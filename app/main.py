from fastapi import FastAPI

from .core.config import get_settings
from .core.logging_config import configure_logging
from .routes.health import health_router
from .routes.leads import leads_router
from .routes.training import training_router
from .routes.agent import agent_router, webhook_router


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="Real Estate AI Agent API", version="0.1.0")

    # Routers
    app.include_router(health_router, prefix="/api")
    app.include_router(leads_router, prefix="/api")
    app.include_router(training_router, prefix="/api")
    app.include_router(agent_router, prefix="/api")
    app.include_router(webhook_router, prefix="/api")

    return app


app = create_app()


# In app/main.py, add:

@app.get("/")
async def root():
    return {"status": "ok", "message": "Real Estate AI Agent API is running"}