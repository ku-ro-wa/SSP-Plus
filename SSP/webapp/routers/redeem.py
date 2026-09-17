# webapp/routers/redeem.py
#
# Phone-side counterpart to upload.py, for a scan the KIOSK created and
# needs to hand OUT rather than take in: the kiosk shows a QR + OTP for this
# page (screens/scan_result), the user opens it on their own phone, and from
# here can either download the PDF directly or have it emailed. Re-auth on
# the follow-up actions is done by resubmitting session_id+otp as hidden
# form fields rather than inventing a new token system — this works because
# SessionManager.verify_otp() short-circuits to a success once a session is
# already 'verified' (see managers/session_manager.py).

from email.message import EmailMessage
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from config import get_config
from webapp.dependencies import get_session_manager, get_smtp_client

router = APIRouter()

# Points at SSP/webapp/templates/ (this file lives in SSP/webapp/routers/,
# so .parent.parent gets us back up to webapp/)
templates = Jinja2Templates(
    directory=Path(__file__).resolve().parent.parent / "templates"
)


@router.get("/redeem", response_class=HTMLResponse)
async def redeem_form(request: Request):
    return templates.TemplateResponse(request, "redeem.html", {"request": request})


@router.post("/redeem", response_class=HTMLResponse)
async def redeem_verify(
    request: Request,
    otp: str = Form(...),
    session_manager=Depends(get_session_manager),
):
    success, message, files, session_id = session_manager.verify_otp_for_source_with_id(
        "scan", otp.strip()
    )
    if not success:
        return templates.TemplateResponse(
            request, "redeem.html", {"request": request, "error": message}, status_code=400,
        )

    return templates.TemplateResponse(
        request, "redeem_actions.html",
        {"request": request, "session_id": session_id, "otp": otp.strip(), "files": files},
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
