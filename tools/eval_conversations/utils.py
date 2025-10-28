from __future__ import annotations

import hashlib
from typing import Iterable


def stable_id(parts: Iterable[str]) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8", errors="ignore"))
        h.update(b"|")
    return h.hexdigest()[:16]


