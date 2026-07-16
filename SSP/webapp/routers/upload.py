import base64

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from webapp.dependencies import get_wifi_adapter

router = APIRouter()


@router.get("/upload", response_class=HTMLResponse)
async def upload_form():
    return """
    <html>
        <body>
            <form action="/upload" enctype="multipart/form-data" method="post">
                <input name="file" type="file">
                <input name="metadata" type="text" placeholder="Metadata">
                <input type="submit">
            </form>
        </body>
    </html>
    """


@router.post("/upload", response_class=HTMLResponse)
async def upload_file(
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
        raise HTTPException(status_code=400, detail=message)

    qr_b64 = base64.b64encode(session.qr_bytes).decode("ascii")
    return f"""
    <html>
        <body>
            <h1>Upload received</h1>
            <p>Scan this QR code at the kiosk, or enter the code manually.</p>
            <img src="data:image/png;base64,{qr_b64}" alt="Pickup QR code">
            <p>Code: <strong>{session.otp}</strong></p>
            <p>Expires at: {session.expires_at.isoformat()}</p>
        </body>
    </html>
    """
