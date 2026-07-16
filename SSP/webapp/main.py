# webapp/main.py
from fastapi import FastAPI

from config import get_config
from webapp.routers import health, upload

config = get_config()

# /docs (Swagger UI) and /redoc are FastAPI's auto-generated API explorers,
# built from route type hints. Handy in dev, but project_objectives.txt
# requires them off in production, so passing None disables both.
docs_url = "/docs" if config.docs_enabled else None
redoc_url = "/redoc" if config.docs_enabled else None

app = FastAPI(title="AIO SPARK", docs_url=docs_url, redoc_url=redoc_url)

app.include_router(health.router)
app.include_router(upload.router)