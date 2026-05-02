"""
whats_new — Composite recent activity synthesis tool.

Killer demo phrase: "Шо слышно?" / "What's new?"

Aggregates last N days of activity from:
- Multi-project folders (Desktop/projects/*, skip Attack!)
- Brave bookmarks (recently added)
- Telegram Saved Messages export (recent messages)
- MemPalace drawers (recent verbatim content) — optional, only if available

Returns Markdown-formatted synthesis ready for Claude to present.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .sources import projects as projects_src
from .sources import bookmarks as bookmarks_src
from .sources import tg_export as tg_src


def _format_project_section(items: list[dict]) -> str:
    """Group project items by project name, format as Markdown."""
    if not items:
        return ""

    by_project: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_project[it.get("project", "unknown")].append(it)

    lines = ["## 🗂 Projects activity\n"]
    for proj, files in sorted(by_project.items()):
        lines.append(f"### {proj}")
        # Show top 5 most-recent files per project
        for f in files[:5]:
            date_short = f.get("date", "")[:10]
            title = f.get("title", "")
            rel = f.get("rel_path", "")
            lines.append(f"- `{rel}` — {title} ({date_short})")
        if len(files) > 5:
            lines.append(f"- _...and {len(files) - 5} more files_")
        lines.append("")
    return "\n".join(lines)


def _format_bookmarks_section(items: list[dict]) -> str:
    """Format bookmark items as Markdown list."""
    if not items:
        return ""
    lines = ["## 🔖 Bookmarks added\n"]
    for b in items[:15]:
        date_short = b.get("date", "")[:10]
        title = b.get("title", "")
        url = b.get("url", "")
        folder = b.get("folder", "")
        if folder:
            lines.append(f"- **{title}** ({date_short}, _{folder}_)")
        else:
            lines.append(f"- **{title}** ({date_short})")
        if url:
            lines.append(f"  {url}")
    if len(items) > 15:
        lines.append(f"\n_...and {len(items) - 15} more bookmarks_")
    return "\n".join(lines) + "\n"


def _format_tg_section(items: list[dict]) -> str:
    """Format TG saved messages section."""
    if not items:
        return ""
    lines = ["## 💬 Telegram Saved highlights\n"]
    for m in items[:15]:
        date_short = m.get("date", "")[:10]
        title = m.get("title", "")
        media = m.get("media_type")
        if media:
            lines.append(f"- _{media}_: {title} ({date_short})")
        else:
            lines.append(f"- {title} ({date_short})")
    if len(items) > 15:
        lines.append(f"\n_...and {len(items) - 15} more saved items_")
    return "\n".join(lines) + "\n"


def _format_palace_section(palace_items: list[dict]) -> str:
    """Format MemPalace drawers section (if available)."""
    if not palace_items:
        return ""
    lines = ["## 🧠 Palace drawers (recent)\n"]
    for d in palace_items[:10]:
        wing = d.get("wing", "?")
        room = d.get("room", "?")
        snippet = (d.get("content", "")[:120] + "...") if len(d.get("content", "")) > 120 else d.get("content", "")
        lines.append(f"- [{wing}/{room}] {snippet}")
    if len(palace_items) > 10:
        lines.append(f"\n_...and {len(palace_items) - 10} more drawers_")
    return "\n".join(lines) + "\n"


def _query_mempalace_recent(days: int) -> list[dict]:
    """
    Best-effort query to MemPalace for recent drawers.

    Uses internal mempalace API directly (we're in the same package).
    Returns [] if palace unavailable or query fails.
    """
    try:
        from mempalace.mcp_server import _get_collection, _fetch_all_metadata, _no_palace
        if _no_palace():
            return []
        col = _get_collection(create=False)
        if not col:
            return []
        meta = _fetch_all_metadata(col)
        if not meta:
            return []

        # Filter by recency (drawers have created_at unix timestamp metadata)
        import time as _time
        cutoff = _time.time() - (days * 86400)

        items = []
        # meta is dict with 'ids', 'metadatas', 'documents'
        ids = meta.get("ids", []) or []
        metadatas = meta.get("metadatas", []) or []
        documents = meta.get("documents", []) or []

        for idx, mdata in enumerate(metadatas):
            if not isinstance(mdata, dict):
                continue
            created = mdata.get("created_at") or mdata.get("timestamp") or 0
            try:
                created = float(created)
            except (TypeError, ValueError):
                created = 0.0
            if created < cutoff:
                continue

            doc = documents[idx] if idx < len(documents) else ""
            items.append({
                "id": ids[idx] if idx < len(ids) else "",
                "wing": mdata.get("wing", "?"),
                "room": mdata.get("room", "?"),
                "content": doc or "",
                "date": created,
            })

        items.sort(key=lambda x: x.get("date", 0), reverse=True)
        return items
    except Exception:
        # Any error → just skip palace section gracefully
        return []


def whats_new(days: int = 7, focus: str | None = None) -> dict:
    """
    Composite synthesis of recent activity across all sources.

    Args:
        days: lookback window (default 7)
        focus: optional project name OR topic — narrows projects + filters keyword

    Returns:
        dict with 'summary' (markdown) + 'counts' per source.
    """
    # Sanitize
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 7
    days = max(1, min(days, 90))

    # Gather sources
    proj_items = projects_src.recent_activity(days=days, project=focus if focus else None)
    bookmark_items = bookmarks_src.recent(days=days)
    tg_items = tg_src.recent(days=days)
    palace_items = _query_mempalace_recent(days=days)

    # If focus is a topic (not a project name), filter via keyword
    if focus:
        project_names = {p["name"] for p in projects_src.list_projects()}
        if focus not in project_names:
            f_low = focus.lower()
            proj_items = [
                p for p in proj_items
                if f_low in p.get("title", "").lower() or f_low in p.get("content", "").lower()
            ]
            bookmark_items = [
                b for b in bookmark_items
                if f_low in b.get("title", "").lower() or f_low in b.get("url", "").lower()
            ]
            tg_items = [
                t for t in tg_items
                if f_low in t.get("title", "").lower() or f_low in t.get("content", "").lower()
            ]

    # Build markdown
    parts = []
    parts.append(f"# 🗞 Шо слышно? (last {days} days)\n")
    if focus:
        parts.append(f"**Focus**: `{focus}`\n")

    parts.append(_format_project_section(proj_items))
    parts.append(_format_bookmarks_section(bookmark_items))
    parts.append(_format_tg_section(tg_items))
    parts.append(_format_palace_section(palace_items))

    summary_md = "\n".join(p for p in parts if p)

    # Final fallback: if nothing found
    if not (proj_items or bookmark_items or tg_items or palace_items):
        summary_md = (
            f"# 🗞 Шо слышно? (last {days} days)\n\n"
            f"Тихо — в этот период ничего значимого не зафиксировано "
            f"в сканируемых источниках.\n\n"
            f"_Sources checked: projects folder, Brave bookmarks, TG export, MemPalace drawers._"
        )

    return {
        "summary": summary_md,
        "counts": {
            "projects": len(proj_items),
            "bookmarks": len(bookmark_items),
            "tg_saved": len(tg_items),
            "palace_drawers": len(palace_items),
        },
        "days": days,
        "focus": focus,
    }
