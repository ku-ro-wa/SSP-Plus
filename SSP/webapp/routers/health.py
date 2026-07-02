# webapp/routers/health.py
#
# An APIRouter is a mini-FastAPI app: define routes here, then main.py
# mounts it onto the real app with app.include_router(). Every future
# module (sessions, upload, admin) gets its own router file like this one.

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}
