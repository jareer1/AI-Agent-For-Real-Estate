from __future__ import annotations

import math
import os
import re
from typing import Dict, List, Optional, Tuple

# Optional OpenAI embeddings for true cosine similarity
_OPENAI_CLIENT = None
_EMBED_MODEL = "text-embedding-3-small"
try:
    from openai import OpenAI
    if os.environ.get("OPENAI_API_KEY"):
        _OPENAI_CLIENT = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
except Exception:
    _OPENAI_CLIENT = None


def _tokenize(text: str) -> List[str]:
    return re.findall(r"\w+", (text or "").lower())


def rouge_l(pred: str, ref: str) -> float:
    # Simple LCS-based ROUGE-L f-score
    a = _tokenize(pred)
    b = _tokenize(ref)
    if not a or not b:
        return 0.0
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    lcs = dp[len(a)][len(b)]
    prec = lcs / len(a)
    rec = lcs / len(b)
    if prec + rec == 0:
        return 0.0
    return (2 * prec * rec) / (prec + rec)


def _cosine_from_tokens(pred: str, ref: str) -> float:
    sa = set(_tokenize(pred))
    sb = set(_tokenize(ref))
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    denom = math.sqrt(len(sa) * len(sb))
    return inter / denom


def _cosine_from_embeddings(pred: str, ref: str) -> Optional[float]:
    if not _OPENAI_CLIENT:
        return None
    try:
        # Guard against empty strings
        p = (pred or "").strip()
        r = (ref or "").strip()
        if not p or not r:
            return 0.0
        resp = _OPENAI_CLIENT.embeddings.create(model=_EMBED_MODEL, input=[p, r])
        va = resp.data[0].embedding
        vb = resp.data[1].embedding
        # cosine similarity
        dot = sum(a * b for a, b in zip(va, vb))
        na = math.sqrt(sum(a * a for a in va))
        nb = math.sqrt(sum(b * b for b in vb))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)
    except Exception:
        return None


ACTION_LABELS = {
    "follow_up": ["checking in", "follow up", "just making sure", "how did"],
    "schedule": ["schedule", "set up", "what time", "when works"],
    "referral": ["referral", "locator", "how did you hear", "choose locator"],
    "rebate": ["$200", "rebate", "free move", "zelle"],
    "pricing": ["$", "free", "special", "weeks free", "prorate", "deposit"],
    "requirements": ["income", "credit", "background", "qualif", "3x", "2.5x"],
}


def _label_action(text: str) -> str:
    t = (text or "").lower()
    best = ("none", 0)
    for label, keys in ACTION_LABELS.items():
        score = sum(1 for k in keys if k in t)
        if score > best[1]:
            best = (label, score)
    return best[0]


ENTITY_PATTERNS = {
    "currency": re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?"),
    "weeks": re.compile(r"\b\d+\s*(?:week|weeks)\b"),
    "months": re.compile(r"\b\d+\s*(?:month|months)\b"),
    "units": re.compile(r"\bunit\s*#?\s*\w+\b", re.IGNORECASE),
    "dates": re.compile(r"\b(?:\d{1,2}/\d{1,2}|\d{1,2}[/-]\d{1,2}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", re.IGNORECASE),
}


def _extract_entities(text: str) -> Dict[str, List[str]]:
    res: Dict[str, List[str]] = {}
    for k, pat in ENTITY_PATTERNS.items():
        res[k] = pat.findall(text or "")
    return res


def _entity_overlap(a: Dict[str, List[str]], b: Dict[str, List[str]]) -> float:
    scores: List[float] = []
    for k in ENTITY_PATTERNS.keys():
        sa = set(a.get(k, []))
        sb = set(b.get(k, []))
        if not sa and not sb:
            continue
        if not sa or not sb:
            scores.append(0.0)
        else:
            inter = len(sa & sb)
            union = len(sa | sb)
            scores.append(inter / union)
    return sum(scores) / len(scores) if scores else 0.0


def _sentence_count(text: str) -> int:
    # naive sentence splitter on ., !, ?
    s = re.split(r"[.!?]+\s+", (text or "").strip())
    return len([x for x in s if x])


def _has_cta(text: str) -> bool:
    p = (text or "").lower()
    return any(
        key in p
        for key in [
            "let me know",
            "what time",
            "when works",
            "would you like",
            "are you looking",
            "can you",
            "please send",
            "confirm",
            "schedule",
            "book",
        ]
    ) or ("?" in p)


def style_compliance(pred: str, ref: str) -> Dict[str, bool]:
    p = (pred or "")
    pl = p.lower()
    # Warm acknowledgement
    polite = any(w in pl for w in ["hi", "hey", "good morning", "thanks", "thank you", "got it", "sounds good", "okay"])
    # Exactly one clear CTA / question
    cta = _has_cta(p)
    single_question = p.count("?") <= 1
    # Keep it short: 1-2 sentences
    short = _sentence_count(p) <= 2
    # Avoid excessive emojis and ALL CAPS
    emoji_ok = len(re.findall(r"[\U0001F300-\U0001FAFF]", p)) <= 1
    caps_ok = not re.search(r"\b[A-Z]{4,}\b", p)
    # Avoid error or obvious failure states
    no_error = not pl.startswith("__error__")
    return {
        "polite": polite,
        "cta_present": cta,
        "single_question": single_question,
        "short": short,
        "emoji_ok": emoji_ok,
        "caps_ok": caps_ok,
        "no_error": no_error,
    }


def score_item(pred: str, ref: str) -> Dict[str, float]:
    # Similarity: prefer embeddings if available, else token-Jaccard
    c_emb = _cosine_from_embeddings(pred, ref)
    c = c_emb if c_emb is not None else _cosine_from_tokens(pred, ref)
    r = rouge_l(pred, ref)
    la = _label_action(ref)
    lp = _label_action(pred)
    action_match = 1.0 if la == lp else 0.0
    ea = _extract_entities(ref)
    ep = _extract_entities(pred)
    ent = _entity_overlap(ep, ea)
    style = style_compliance(pred, ref)
    style_score = sum(1.0 if v else 0.0 for v in style.values()) / max(len(style), 1)

    # Length penalty: if prediction is much longer than ref (>1.5x), apply small penalty
    len_pred = len(pred or "")
    len_ref = len(ref or "")
    length_ratio = (len_pred / max(len_ref, 1)) if len_ref else 1.0
    length_penalty = 0.0
    if length_ratio > 1.5:
        length_penalty = min(0.1, 0.02 * (length_ratio - 1.5))  # cap at 0.1

    # Weighted total
    total = (
        0.35 * c
        + 0.15 * r
        + 0.20 * action_match
        + 0.15 * ent
        + 0.15 * style_score
    )
    total = max(0.0, total - length_penalty)
    return {
        "cosine": c,
        "rougeL": r,
        "action_match": action_match,
        "entity": ent,
        "style": style_score,
        "total": total,
    }


