import base64
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from webapp.dependencies import get_wifi_adapter

print("UPLOAD ROUTER IMPORTED")

router = APIRouter()

# Points at SSP/webapp/templates/ (this file lives in SSP/webapp/routers/,
# so .parent.parent gets us back up to webapp/)
templates = Jinja2Templates(
    directory=Path(__file__).resolve().parent.parent / "templates"
)


@router.get("/upload", response_class=HTMLResponse)
async def upload_form(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
        },
    )


@router.post("/upload", response_class=HTMLResponse)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    metadata: str = Form(None),
    wifi_adapter=Depends(get_wifi_adapter),
):
    success, message, session = wifi_adapter.handle_upload(
        file_obj=file.file,
        filename=file.filename,
        content_type=file.content_type,
        metadata=metadata,
    )

    if not success:
        # Re-show the upload page with the error banner
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "request": request,
                "error": message,
            },
            status_code=400,
        )

    qr_b64 = base64.b64encode(session.qr_bytes).decode("ascii")
    
    return templates.TemplateResponse(
        request,
        "success.html",
        {
            "request": request,
            "qr": qr_b64,
            "otp": session.otp,
        },
    )
    """
    from pathlib import Path

    print("USING TEMPLATE:", templates.directory)
    print("SUCCESS FILE:",
        Path(templates.directory) / "success.html")

    return templates.TemplateResponse(
        request,
        "success.html",
        {
            "request": request,
            "qr": qr_b64,
            "otp": session.otp,
        },
    )
    """



