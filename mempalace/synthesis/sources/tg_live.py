"""
tg_live — Telegram Saved Messages live reader via MTProto (telethon).

Status: v0.2 SCAFFOLD — requires user-supplied credentials before activation.

Setup:
1. Get api_id and api_hash from https://my.telegram.org → API Development Tools.
2. Save to project root .env (which is gitignored):
   TG_API_ID=12345678
   TG_API_HASH=abcdef0123456789...
   TG_PHONE=+1234567890
3. First run will prompt for SMS code (one-time interactive). Session saved to
   .tg-session/polypalace.session and reused thereafter (no further prompts).

Privacy:
- Credentials NEVER committed (.env in .gitignore)
- Session files NEVER committed (.tg-session/*.session in .gitignore)
- All reads local — no third-party services involved

Output shape (matches tg_export.py for compatibility):
{
    "source": "tg_saved_live",
    "id": int,
    "date": str (ISO 8601),
    "_unix_ts": float,
    "title": str (first 60 chars or [media_type]),
    "content": str (full text),
    "media_type": str | None,
}

Reads ONLY from "me" peer (Saved Messages). Other chats not exposed.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

# Telethon is an optional dep — gracefully degrade if not installed
try:
    from telethon import TelegramClient
    from telethon.tl.types import (
        Message,
        MessageMediaPhoto,
        MessageMediaDocument,
        MessageMediaWebPage,
    )
    TELETHON_AVAILABLE = True
except ImportError:
    TELETHON_AVAILABLE = False
    TelegramClient = None  # type: ignore

# Optional: load .env automatically
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parents[3] / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass


SESSION_DIR = Path(__file__).resolve().parents[3] / ".tg-session"
SESSION_NAME = "polypalace"


def _phones() -> list[str]:
    """
    Return list of TG account phone numbers to access.

    Priority:
      1. TG_PHONES (comma-separated, multi-account support)
      2. TG_PHONE (single account, backward compat)
    """
    multi = os.environ.get("TG_PHONES", "").strip()
    if multi:
        return [p.strip() for p in multi.split(",") if p.strip()]
    single = os.environ.get("TG_PHONE", "").strip()
    return [single] if single else []


def _session_path_for(phone: str) -> str:
    """Per-phone session file path. Use phone last-6-digits as suffix to avoid + and special chars."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "".join(c for c in phone if c.isdigit())[-6:] or "default"
    return str(SESSION_DIR / f"{SESSION_NAME}_{suffix}")


def _credentials_available() -> bool:
    """Check if api creds + at least one phone are set."""
    return bool(os.environ.get("TG_API_ID")) and bool(os.environ.get("TG_API_HASH")) and bool(_phones())


def _media_type_label(msg) -> str | None:
    """Extract a short media type label from a telethon Message."""
    if not msg.media:
        return None
    if isinstance(msg.media, MessageMediaPhoto):
        return "photo"
    if isinstance(msg.media, MessageMediaDocument):
        doc = getattr(msg.media, "document", None)
        if doc:
            mime = getattr(doc, "mime_type", "") or ""
            if mime.startswith("video"):
                return "video"
            if mime.startswith("audio"):
                if "voice" in mime or any(getattr(a, "voice", False) for a in (doc.attributes or [])):
                    return "voice"
                return "audio"
            if "image" in mime:
                return "image"
            if "pdf" in mime:
                return "pdf"
            return "file"
        return "document"
    if isinstance(msg.media, MessageMediaWebPage):
        return "weblink"
    return type(msg.media).__name__.replace("MessageMedia", "").lower()


def _parse_message(msg) -> dict | None:
    """Convert telethon Message to our standard shape."""
    if not isinstance(msg, Message):
        return None
    text = msg.message or ""
    media_label = _media_type_label(msg)
    if not text and not media_label:
        return None
    title = (text[:60].replace("\n", " ") if text else f"[{media_label}]")
    ts = msg.date.timestamp() if msg.date else 0.0
    iso = msg.date.astimezone(timezone.utc).isoformat() if msg.date else ""
    return {
        "source": "tg_saved_live",
        "id": msg.id,
        "date": iso,
        "_unix_ts": ts,
        "title": title,
        "content": text or f"[{media_label}]",
        "media_type": media_label,
    }


async def _fetch_one_account(phone: str, limit: int, offset_date) -> list[dict]:
    """Fetch Saved Messages for a single TG account by phone."""
    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]
    session_path = _session_path_for(phone)

    client = TelegramClient(session_path, api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        # Don't raise — gracefully skip this account so other authorized
        # accounts still work. Login script handles auth setup separately.
        return []

    # Tag items with the phone account so dedup keys remain unique across accounts
    suffix = "".join(c for c in phone if c.isdigit())[-6:] or "?"
    out = []
    try:
        async for msg in client.iter_messages(
            "me",
            limit=limit,
            offset_date=offset_date,
        ):
            item = _parse_message(msg)
            if item:
                # Make id unique per account (telethon msg.id is per-chat, can collide between accounts)
                item["id"] = f"{suffix}:{item['id']}"
                item["account"] = suffix
                out.append(item)
    finally:
        await client.disconnect()
    return out


async def _fetch_async(limit: int = 200, offset_date=None) -> list[dict]:
    """Async fetch of Saved Messages across ALL configured accounts."""
    phones = _phones()
    if not phones:
        return []
    combined = []
    for phone in phones:
        try:
            items = await _fetch_one_account(phone, limit, offset_date)
            combined.extend(items)
        except Exception:
            # Individual account failure doesn't break the rest
            continue
    combined.sort(key=lambda x: x.get("_unix_ts", 0), reverse=True)
    return combined


def list_all(limit: int = 200) -> list[dict]:
    """Return parsed TG saved messages from live session."""
    if not TELETHON_AVAILABLE or not _credentials_available():
        return []
    try:
        return asyncio.run(_fetch_async(limit=limit))
    except Exception:
        return []


def recent(days: int = 7) -> list[dict]:
    """Return messages from last N days, sorted DESC."""
    if not TELETHON_AVAILABLE or not _credentials_available():
        return []
    import time as _time
    cutoff = _time.time() - (days * 86400)
    items = list_all(limit=500)
    items = [m for m in items if m.get("_unix_ts", 0) >= cutoff]
    items.sort(key=lambda x: x.get("_unix_ts", 0), reverse=True)
    return items


def search(query: str, days: int | None = None, text_only: bool = False) -> list[dict]:
    """Substring search over live Saved Messages."""
    if not TELETHON_AVAILABLE or not _credentials_available():
        return []
    if not query or not query.strip():
        return []
    q_low = query.lower().strip()
    items = list_all(limit=1000)

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


async def _delete_async(account_suffix: str, msg_ids: list[int]) -> dict:
    """Delete specified Saved Messages from a single account session."""
    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    session_path = str(SESSION_DIR / f"{SESSION_NAME}_{account_suffix}")

    client = TelegramClient(session_path, api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        return {"deleted": 0, "error": f"account {account_suffix} not authorized"}
    try:
        # delete from "me" (Saved Messages); revoke=True ensures full deletion
        result = await client.delete_messages("me", msg_ids, revoke=True)
        # result is list of Updates objects; sum the count
        count = sum(getattr(r, "pts_count", len(msg_ids) if msg_ids else 0) for r in result) if result else len(msg_ids)
        return {"deleted": count, "ids": msg_ids, "account": account_suffix}
    except Exception as e:
        return {"deleted": 0, "error": str(e), "ids": msg_ids, "account": account_suffix}
    finally:
        await client.disconnect()


def take_in_work(message_id: str, confirm: bool = False) -> dict:
    """
    Delete a TG Saved Message — used when user takes a task/idea "into work".

    Args:
        message_id: composite ID from whats_new/surface_ideas output, format "<suffix>:<id>"
                    (e.g. "196993:42" — last-6-digits-of-phone : telegram-msg-id).
                    If raw int passed, defaults to first configured account.
        confirm: must be True. Safety gate to prevent accidental delete via LLM hallucination.

    Returns:
        dict with deleted count + status. On error: {"deleted": 0, "error": ...}
    """
    if not confirm:
        return {
            "deleted": 0,
            "error": "Refusing to delete without explicit confirm=True. "
                     "Caller must pass confirm=True after user-confirmed intent.",
        }
    if not TELETHON_AVAILABLE or not _credentials_available():
        return {"deleted": 0, "error": "telethon or credentials unavailable"}

    # Parse composite ID
    if isinstance(message_id, int):
        # Single-account legacy path: assume primary account
        phones = _phones()
        if not phones:
            return {"deleted": 0, "error": "no TG_PHONE configured"}
        suffix = "".join(c for c in phones[0] if c.isdigit())[-6:] or "default"
        ids = [message_id]
    else:
        s = str(message_id)
        if ":" in s:
            suffix, raw_id = s.split(":", 1)
            try:
                ids = [int(raw_id)]
            except ValueError:
                return {"deleted": 0, "error": f"bad message_id format: {message_id}"}
        else:
            phones = _phones()
            if not phones:
                return {"deleted": 0, "error": "no TG_PHONE configured"}
            suffix = "".join(c for c in phones[0] if c.isdigit())[-6:] or "default"
            try:
                ids = [int(s)]
            except ValueError:
                return {"deleted": 0, "error": f"bad message_id: {message_id}"}

    try:
        return asyncio.run(_delete_async(suffix, ids))
    except Exception as e:
        return {"deleted": 0, "error": str(e)}


def cli_login() -> None:
    """
    One-time interactive login for telethon session.

    Run via:  python -m mempalace.synthesis.sources.tg_live login

    Prompts for SMS code (sent to your TG account by Telegram).
    After success, session saved to .tg-session/polypalace.session and
    reused on subsequent imports — no further prompts.
    """
    if not TELETHON_AVAILABLE:
        print("ERROR: telethon not installed. Run: pip install telethon python-dotenv")
        return
    if not _credentials_available():
        missing = [k for k in ("TG_API_ID", "TG_API_HASH", "TG_PHONE") if not os.environ.get(k)]
        print(f"ERROR: missing env vars: {missing}")
        print(f"Add them to .env at project root, then re-run.")
        return

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    session_path = str(SESSION_DIR / SESSION_NAME)
    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]
    phone = os.environ["TG_PHONE"]

    async def _run():
        client = TelegramClient(session_path, api_id, api_hash)
        await client.start(phone=phone)
        me = await client.get_me()
        print(f"OK — logged in as {me.first_name} (@{me.username or 'no-username'})")
        print(f"Session saved at: {session_path}.session")
        print(f"PolyPalace tg_live source now active. Re-import will use saved session.")
        await client.disconnect()

    asyncio.run(_run())


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        cli_login()
    else:
        print("Usage: python -m mempalace.synthesis.sources.tg_live login")
