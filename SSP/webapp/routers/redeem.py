# webapp/routers/redeem.py
#
# Phone-side counterpart to upload.py, for a scan the KIOSK created and
# needs to hand OUT rather than take in: the kiosk shows a QR + OTP for this
# page (screens/scan_result), the user opens it on their own phone, and from
# here can either download the PDF directly or have it emailed. Re-auth on
# the follow-up actions is done by resubmitting session_id+otp as hidden
# form fields rather than inventing a new token system — this works because
# SessionManager.verify_otp() answers a session already 'verified' with a
# success, as long as the OTP still matches (see managers/session_manager.py).
#
# Wrong codes are rate-limited per client (webapp/rate_limit.py, issue #104):
# this page is unauthenticated and a pickup code is only 6 digits, so a guess
# here must not be free. The kiosk keypad's own lockout is a separate counter.

from email.message import EmailMessage
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from config import get_config
# The same error_log category as the kiosk keypad's lockout, so Kiosk Admin and
# the Admin Dashboard show one kind of row for wrong pickup codes.
from managers.pickup_code_lockout import ERROR_SOURCE
from webapp.dependencies import (
    get_db, get_pickup_code_limiter, get_session_manager, get_smtp_client,
)
from webapp.rate_limit import MAX_ATTEMPTS, WINDOW_SECONDS, blocked_message

router = APIRouter()

# Points at SSP/webapp/templates/ (this file lives in SSP/webapp/routers/,
# so .parent.parent gets us back up to webapp/)
templates = Jinja2Templates(
    directory=Path(__file__).resolve().parent.parent / "templates"
)


@router.get("/redeem", response_class=HTMLResponse)
async def redeem_form(request: Request):
    return templates.TemplateResponse(request, "redeem.html", {"request": request})


def _client_id(request: Request) -> str:
    # On the Hotspot this is the phone's address, which is the whole identity
    # the unauthenticated Portal has. A missing client shares one budget.
    return request.client.host if request.client else "unknown"


def _too_many(request: Request, seconds: int):
    return templates.TemplateResponse(
        request, "redeem.html",
        {"request": request, "error": blocked_message(seconds)},
        status_code=429,
        headers={"Retry-After": str(int(seconds))},
    )


def _log_lockout(db):
    # One row per lockout, not per refused attempt. No client address: it is a
    # customer's phone (ADR 0006 keeps the Portal out of identifying people).
    message = (f"Redeem form locked for {int(WINDOW_SECONDS) // 60} min after "
               f"{MAX_ATTEMPTS} wrong pickup codes")
    try:
        db.log_error(ERROR_SOURCE, message, "Redeem Portal")
    except Exception as e:
        print(f"Redeem Portal: could not log lockout: {e}")


@router.post("/redeem", response_class=HTMLResponse)
async def redeem_verify(
    request: Request,
    otp: str = Form(...),
    session_manager=Depends(get_session_manager),
    limiter=Depends(get_pickup_code_limiter),
    db=Depends(get_db),
):
    client = _client_id(request)
    blocked = limiter.blocked_for(client)
    if blocked:
        return _too_many(request, blocked)

    result = session_manager.verify_typed_otp("scanner", otp.strip())
    if not result.success:
        # Only a code that matched no Session counts; a real code that is
        # expired or locked out is not a guess and must not cost an attempt.
        if not result.matched:
            blocked = limiter.record_failure(client)
            if blocked:
                _log_lockout(db)
                return _too_many(request, blocked)
        return templates.TemplateResponse(
            request, "redeem.html",
            {"request": request, "error": result.message},
            status_code=400,
        )

    limiter.record_success(client)
    return templates.TemplateResponse(
        request, "redeem_actions.html",
        {
            "request": request, "session_id": result.session_id,
            "otp": otp.strip(), "files": result.files,
        },
    )


@router.post("/redeem/download")
async def redeem_download(
    request: Request,
    session_id: str = Form(...),
    otp: str = Form(...),
    session_manager=Depends(get_session_manager),
):
    success, message, files = session_manager.verify_otp(session_id, otp.strip())
    if not success or not files:
        return templates.TemplateResponse(
            request, "redeem.html", {"request": request, "error": message}, status_code=400,
        )

    f = files[0]
    return FileResponse(
        f["path"], media_type="application/pdf",
        filename=f.get("original_filename") or "scan.pdf",
    )


@router.post("/redeem/email", response_class=HTMLResponse)
async def redeem_email(
    request: Request,
    session_id: str = Form(...),
    otp: str = Form(...),
    recipient: str = Form(...),
    session_manager=Depends(get_session_manager),
    smtp_client=Depends(get_smtp_client),
):
    success, message, files = session_manager.verify_otp(session_id, otp.strip())
    if not success or not files:
        return templates.TemplateResponse(
            request, "redeem.html", {"request": request, "error": message}, status_code=400,
        )

    f = files[0]
    msg = EmailMessage()
    msg["Subject"] = "Your scanned document"
    msg["From"] = get_config().email_user
    msg["To"] = recipient
    msg.set_content("Your scanned document is attached.")
    with open(f["path"], "rb") as fh:
        msg.add_attachment(
            fh.read(), maintype="application", subtype="pdf",
            filename=f.get("original_filename") or "scan.pdf",
        )

    try:
        smtp_client.send(msg)
    except Exception as e:
        return templates.TemplateResponse(
            request, "redeem_actions.html",
            {
                "request": request, "session_id": session_id, "otp": otp,
                "files": files, "error": f"Could not send email: {e}",
            },
            status_code=502,
        )

    return templates.TemplateResponse(
        request, "redeem_actions.html",
        {
            "request": request, "session_id": session_id, "otp": otp,
            "files": files, "sent_to": recipient,
        },
    )
