from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field


class Channel(str, Enum):
    sms = "sms"
    email = "email"
    phone = "phone"
    social = "social"
    unknown = "unknown"


class Role(str, Enum):
    agent = "agent"
    lead = "lead"
    system = "system"


class Stage(str, Enum):
    first_contact = "first_contact"
    sending_list = "sending_list"
    selecting_favorites = "selecting_favorites"
    touring = "touring"
    applying = "applying"
    approval = "approval"
    post_close = "post_close"
    renewal = "renewal"


class StageV2(str, Enum):
    qualifying = "qualifying"
    working = "working"
    touring = "touring"
    applied = "applied"
    approved = "approved"
    closed = "closed"
    post_close_nurture = "post_close_nurture"


def map_text_to_stage_v2(text: str, current: StageV2 | None = None) -> StageV2:
    lower = (text or "").lower()
    if any(k in lower for k in ["apply", "application", "applied"]):
        return StageV2.applied
    if any(k in lower for k in ["approved", "approval"]):
        return StageV2.approved
    if any(k in lower for k in ["tour", "showing", "schedule", "touring"]):
        return StageV2.touring
    if any(k in lower for k in ["close", "closed", "lease signed", "moved in"]):
        return StageV2.closed
    if any(k in lower for k in ["follow up", "referral", "post-close", "move in", "nurture"]):
        return StageV2.post_close_nurture
    if any(k in lower for k in ["list", "options", "send", "working", "credit", "docs"]):
        return StageV2.working
    if any(k in lower for k in ["budget", "move", "when", "bed", "bath", "qualify", "qualifying"]):
        return StageV2.qualifying
    return current or StageV2.qualifying


def map_stage_legacy_to_v2(stage: Stage | None) -> StageV2:
    if stage is None:
        return StageV2.qualifying
    mapping = {
        Stage.first_contact: StageV2.qualifying,
        Stage.sending_list: StageV2.working,
        Stage.selecting_favorites: StageV2.working,
        Stage.touring: StageV2.touring,
        Stage.applying: StageV2.applied,
        Stage.approval: StageV2.approved,
        Stage.post_close: StageV2.post_close_nurture,
        Stage.renewal: StageV2.post_close_nurture,
    }
    return mapping.get(stage, StageV2.qualifying)


def map_stage_v2_to_legacy(stage_v2: StageV2) -> Stage:
    reverse = {
        StageV2.qualifying: Stage.first_contact,
        StageV2.working: Stage.sending_list,
        StageV2.touring: Stage.touring,
        StageV2.applied: Stage.applying,
        StageV2.approved: Stage.approval,
        StageV2.closed: Stage.post_close,
        StageV2.post_close_nurture: Stage.post_close,
    }
    return reverse.get(stage_v2, Stage.first_contact)


class Lead(BaseModel):
    id: str
    full_name: str
    phone: str
    email: EmailStr
    budget: Optional[int] = None
    move_date: Optional[str] = None  # ISO string placeholder
    notes: Optional[str] = None


class Message(BaseModel):
    role: Role
    content: str = Field(min_length=1)
    channel: Channel = Channel.unknown
    created_at: Optional[str] = None
    attachments: list[str] = []


class Thread(BaseModel):
    id: str
    lead: Lead
    stage: Stage
    events: list[Message]


