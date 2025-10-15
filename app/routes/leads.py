from fastapi import APIRouter

from ..schemas.common import Lead, Thread, Stage


leads_router = APIRouter(prefix="/leads", tags=["leads"])


@leads_router.post("/threads", response_model=Thread)
def create_thread(thread: Thread) -> Thread:
    # Placeholder in-memory passthrough
    return thread


@leads_router.post("/leads", response_model=Lead)
def upsert_lead(lead: Lead) -> Lead:
    return lead


@leads_router.get("/stages", response_model=list[str])
def list_stages() -> list[str]:
    return [s.value for s in Stage]


