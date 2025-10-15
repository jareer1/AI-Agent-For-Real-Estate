from fastapi import APIRouter


health_router = APIRouter(tags=["health"])


@health_router.get("/healthz")
def healthcheck() -> dict:
    return {"status": "ok"}


