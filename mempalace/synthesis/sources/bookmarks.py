"""
bookmarks — Brave / Chrome bookmarks reader.

Reads the JSON bookmarks file from Brave's profile directory.

Path (Windows): %LOCALAPPDATA%\\BraveSoftware\\Brave-Browser\\User Data\\Default\\Bookmarks
Path (Linux):   ~/.config/BraveSoftware/Brave-Browser/Default/Bookmarks
Path (macOS):   ~/Library/Application Support/BraveSoftware/Brave-Browser/Default/Bookmarks

The file is a JSON document with structure:
{
  "roots": {
    "bookmark_bar": { "children": [...] },
    "other":        { "children": [...] },
    "synced":       { "children": [...] },
  }
}

Each bookmark node has:
- "type": "url" | "folder"
- "name": str
- "url":  str (if type=url)
- "date_added": str (Chrome epoch microseconds since 1601-01-01)
- "children": list[node] (if type=folder)

We flatten and convert to Unix timestamps.

Brave may lock this file while running. We copy to a temp snapshot first.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


# Chrome/Brave epoch: microseconds since 1601-01-01 UTC
# To convert to Unix timestamp: (chrome_us / 1_000_000) - 11_644_473_600
CHROME_EPOCH_OFFSET_S = 11_644_473_600


def _default_bookmarks_path() -> Path | None:
    """Auto-detect Brave bookmarks file path per OS."""
    # Windows
    if os.name == "nt":
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            p = Path(local_app) / "BraveSoftware" / "Brave-Browser" / "User Data" / "Default" / "Bookmarks"
            if p.exists():
                return p
    # Linux
    elif os.uname().sysname == "Linux":
        p = Path.home() / ".config" / "BraveSoftware" / "Brave-Browser" / "Default" / "Bookmarks"
        if p.exists():
            return p
    # macOS
    elif os.uname().sysname == "Darwin":
        p = Path.home() / "Library" / "Application Support" / "BraveSoftware" / "Brave-Browser" / "Default" / "Bookmarks"
        if p.exists():
            return p
    return None


def _bookmarks_path() -> Path | None:
    """Resolve bookmarks path, honoring env override."""
    override = os.environ.get("PERSONAL_CTO_MCP_BOOKMARKS_PATH")
    if override:
        p = Path(override).expanduser()
        if p.exists():
            return p
        return None
    return _default_bookmarks_path()


def _safe_read(path: Path) -> dict | None:
    """Read bookmarks JSON, copying via temp first to avoid file locks."""
    if not path or not path.exists():
        return None
    # Copy to temp (Brave locks file while running)
    fd, tmp = tempfile.mkstemp(prefix="bookmarks-", suffix=".json")
    os.close(fd)
    tmp_path = Path(tmp)
    try:
        shutil.copyfile(path, tmp_path)
        with open(tmp_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def _chrome_us_to_iso(chrome_us: str | int) -> str:
    """Convert Chrome epoch microseconds to ISO 8601 UTC."""
    try:
        us = int(chrome_us)
    except (ValueError, TypeError):
        return ""
    unix_s = (us / 1_000_000) - CHROME_EPOCH_OFFSET_S
    if unix_s <= 0:
        return ""
    try:
        return datetime.fromtimestamp(unix_s, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return ""


def _chrome_us_to_unix(chrome_us: str | int) -> float:
    """Convert Chrome epoch microseconds to Unix timestamp."""
    try:
        us = int(chrome_us)
    except (ValueError, TypeError):
        return 0.0
    return (us / 1_000_000) - CHROME_EPOCH_OFFSET_S


def _flatten(node: dict, folder_path: list[str]) -> list[dict]:
    """Recursively flatten bookmark tree into list of url-typed nodes."""
    out = []
    node_type = node.get("type")
    name = node.get("name", "")

    if node_type == "url":
        out.append({
            "source": "bookmark",
            "title": name,
            "url": node.get("url", ""),
            "folder": " / ".join(folder_path),
            "date": _chrome_us_to_iso(node.get("date_added", "0")),
            "_unix_ts": _chrome_us_to_unix(node.get("date_added", "0")),
        })
    elif node_type == "folder" or "children" in node:
        new_path = folder_path + [name] if name else folder_path
        for child in node.get("children", []):
            out.extend(_flatten(child, new_path))
    return out


def list_all() -> list[dict]:
    """Return all bookmarks as flat list."""
    path = _bookmarks_path()
    data = _safe_read(path) if path else None
    if not data:
        return []
    roots = data.get("roots", {})
    out = []
    for root_key in ("bookmark_bar", "other", "synced"):
        root = roots.get(root_key)
        if root:
            out.extend(_flatten(root, [root_key]))
    return out


def recent(days: int = 7) -> list[dict]:
    """Return bookmarks added in last N days, sorted DESC by date."""
    import time as _time
    cutoff = _time.time() - (days * 86400)
    items = list_all()
    items = [b for b in items if b.get("_unix_ts", 0) >= cutoff]
    items.sort(key=lambda x: x.get("_unix_ts", 0), reverse=True)
    return items


def search(query: str, days: int | None = None) -> list[dict]:
    """Simple substring search over bookmark names + URLs."""
    if not query or not query.strip():
        return []
    q_low = query.lower().strip()
    items = list_all()

    if days:
        import time as _time
        cutoff = _time.time() - (days * 86400)
        items = [b for b in items if b.get("_unix_ts", 0) >= cutoff]

    matches = []
    for b in items:
        title = b.get("title", "").lower()
        url = b.get("url", "").lower()
        folder = b.get("folder", "").lower()
        score = 0
        if q_low in title:
            score += 3
        if q_low in url:
            score += 1
        if q_low in folder:
            score += 1
        if score > 0:
            b_copy = dict(b)
            b_copy["score"] = score
            matches.append(b_copy)

    matches.sort(key=lambda x: x["score"], reverse=True)
    return matches[:20]
