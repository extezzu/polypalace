"""
tg_export — Telegram Desktop export reader (Saved Messages).

How user obtains export:
  Telegram Desktop → Settings → Advanced → Export Telegram Data
    → Saved Messages only → JSON → save to:
    %USERPROFILE%\\Desktop\\tg-export\\result.json (default)

Format (JSON):
{
  "personal_information": {...},
  "messages": [
    {
      "id": int,
      "type": "message",
      "date": "2026-04-15T10:23:45",
      "date_unixtime": "1745321025",
      "from": "Saved Messages",
      "text": str | list (formatted runs),
      "media_type": "photo" | "video_file" | "voice_message" | ...,
      ...
    },
    ...
  ]
}

Output shape (per item):
{
    "source": "tg_saved",
    "date": str (ISO 8601),
    "title": str (first 60 chars of text or media type),
    "content": str (full text or media reference),
    "_unix_ts": float,
    "id": int,
    "media_type": str | None,
}
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _default_path() -> Path:
    """Default path for TG export."""
    return Path.home() / "Desktop" / "tg-export" / "result.json"


def _resolve_path() -> Path | None:
    """Resolve path with env override."""
    override = os.environ.get("PERSONAL_CTO_MCP_TG_EXPORT_PATH")
    if override:
        p = Path(override).expanduser()
        if p.exists():
            return p
        return None
    p = _default_path()
    if p.exists():
        return p
    return None


def _load() -> dict | None:
    """Load TG export JSON."""
    path = _resolve_path()
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _normalize_text(text_field) -> str:
    """TG's `text` can be str OR list of formatted runs. Flatten to str."""
    if isinstance(text_field, str):
        return text_field
    if isinstance(text_field, list):
        parts = []
        for run in text_field:
            if isinstance(run, str):
                parts.append(run)
            elif isinstance(run, dict):
                parts.append(run.get("text", ""))
        return "".join(parts)
    return ""


def _parse_message(msg: dict) -> dict | None:
    """Convert raw TG message to our standard shape."""
    if msg.get("type") != "message":
        return None

    text = _normalize_text(msg.get("text", ""))
    media_type = msg.get("media_type")

    # Build display title
    if text:
        title = text[:60].replace("\n", " ")
    elif media_type:
        title = f"[{media_type}]"
    else:
        return None  # nothing to show

    # Date handling
    unix_ts = msg.get("date_unixtime", "0")
    try:
        ts = float(unix_ts)
    except (TypeError, ValueError):
        ts = 0.0

    iso_date = msg.get("date", "")
    if not iso_date and ts:
        iso_date = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

    return {
        "source": "tg_saved",
        "id": msg.get("id"),
        "date": iso_date,
        "_unix_ts": ts,
        "title": title,
        "content": text or f"[{media_type}]" if media_type else "",
        "media_type": media_type,
    }


def list_all() -> list[dict]:
    """Return all parsed TG saved messages."""
    data = _load()
    if not data:
        return []
    out = []
    for raw in data.get("messages", []):
        item = _parse_message(raw)
        if item:
            out.append(item)
    return out


def recent(days: int = 7) -> list[dict]:
    """Return messages from last N days, sorted DESC."""
    import time as _time
    cutoff = _time.time() - (days * 86400)
    items = list_all()
    items = [m for m in items if m.get("_unix_ts", 0) >= cutoff]
    items.sort(key=lambda x: x.get("_unix_ts", 0), reverse=True)
    return items


def search(query: str, days: int | None = None, text_only: bool = False) -> list[dict]:
    """
    Substring search over TG saved messages.

    Args:
        query: search term
        days: optional time filter
        text_only: if True, exclude items with media_type
    """
    if not query or not query.strip():
        return []
    q_low = query.lower().strip()
    items = list_all()

    if text_only:
        items = [m for m in items if not m.get("media_type")]

    if days:
        import time as _time
        cutoff = _time.time() - (days * 86400)
        items = [m for m in items if m.get("_unix_ts", 0) >= cutoff]

    matches = []
    for m in items:
        content = m.get("content", "").lower()
        title = m.get("title", "").lower()
        score = 0
        if q_low in title:
            score += 2
        if q_low in content:
            score += 1
        if score > 0:
            mc = dict(m)
            mc["score"] = score
            matches.append(mc)

    matches.sort(key=lambda x: x["score"], reverse=True)
    return matches[:20]
