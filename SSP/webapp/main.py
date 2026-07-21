# webapp/main.py
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import get_config
from webapp.routers import health, upload

config = get_config()

# /docs (Swagger UI) and /redoc are FastAPI's auto-generated API explorers,
# built from route type hints. Handy in dev, but project_objectives.txt
# requires them off in production, so passing None disables both.
docs_url = "/docs" if config.docs_enabled else None
redoc_url = "/redoc" if config.docs_enabled else None

app = FastAPI(title="AIO SPARK", docs_url=docs_url, redoc_url=redoc_url)

# Serves everything in SSP/webapp/static/ at the URL path /static/...
# so your HTML's <img src="/static/image.png"> actually resolves.
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(health.router)
app.include_router(upload.router)



# To run both on desktop and mobile: uvicorn webapp.main:app --reload --host 0.0.0.0 --port 8000
# lookback IP: http://<LAN IP>:8000/
# Example: 
# lookback IP: http://192.168.8.180:8000/upload