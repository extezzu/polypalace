"""
surface_ideas — Surface relevant content from sources for current topic context.

Use case: while working on topic X, query "show me what I previously saved about X"
across projects, bookmarks, TG saved messages, and palace drawers.

Different from `whats_new` (recent activity) — this is topic-specific recall.
"""

from __future__ import annotations

from .sources import projects as projects_src
from .sources import bookmarks as bookmarks_src
from .sources import tg_export as tg_src


def _query_mempalace_search(topic: str) -> list[dict]:
    """
    Best-effort query MemPalace semantic search for relevant drawers.

    Returns [] if palace unavailable.
    """
    try:
        from mempalace.mcp_server import tool_search, _no_palace
        if _no_palace():
            return []
        result = tool_search(query=topic, limit=10)
        if not isinstance(result, dict):
            return []
        # tool_search returns dict with 'results' or 'matches' depending on version
        matches = result.get("results") or result.get("matches") or []
        out = []
        for m in matches:
            if not isinstance(m, dict):
                continue
            out.append({
                "wing": m.get("wing", "?"),
                "room": m.get("room", "?"),
                "content": m.get("content") or m.get("document", ""),
                "score": m.get("score") or m.get("distance", 0),
                "id": m.get("id", ""),
            })
        return out
    except Exception:
        return []


def _format_palace_matches(items: list[dict]) -> str:
    if not items:
        return ""
    lines = ["## 🧠 Palace matches (semantic)\n"]
    for m in items[:10]:
        wing = m.get("wing", "?")
        room = m.get("room", "?")
        content = m.get("content", "")
        snippet = content[:200] + ("..." if len(content) > 200 else "")
        lines.append(f"- **[{wing}/{room}]** {snippet}")
    return "\n".join(lines) + "\n"


def _format_project_matches(items: list[dict]) -> str:
    if not items:
        return ""
    lines = ["## 📁 Project file matches (keyword)\n"]
    for it in items[:10]:
        proj = it.get("project", "?")
        rel = it.get("rel_path", "")
        date_short = it.get("date", "")[:10]
        snippet = it.get("content", "")[:200]
        lines.append(f"- **[{proj}]** `{rel}` ({date_short})")
        lines.append(f"  > {snippet}")
    return "\n".join(lines) + "\n"


def _format_bookmark_matches(items: list[dict]) -> str:
    if not items:
        return ""
    lines = ["## 🔖 Bookmark matches\n"]
    for b in items[:10]:
        title = b.get("title", "")
        url = b.get("url", "")
        date_short = b.get("date", "")[:10]
        folder = b.get("folder", "")
        if folder:
            lines.append(f"- **{title}** ({date_short}, _{folder}_)")
        else:
            lines.append(f"- **{title}** ({date_short})")
        if url:
            lines.append(f"  {url}")
    return "\n".join(lines) + "\n"


def _format_tg_matches(items: list[dict]) -> str:
    if not items:
        return ""
    lines = ["## 💬 TG Saved matches\n"]
    for m in items[:10]:
        title = m.get("title", "")
        date_short = m.get("date", "")[:10]
        media = m.get("media_type")
        if media:
            lines.append(f"- _{media}_: {title} ({date_short})")
        else:
            lines.append(f"- {title} ({date_short})")
        snippet = m.get("content", "")[:150]
        if snippet and snippet != title:
            lines.append(f"  > {snippet}")
    return "\n".join(lines) + "\n"


def surface_ideas(
    topic: str,
    sources: str = "all",
    days: int | None = None,
) -> dict:
    """
    Surface relevant content for topic across sources.

    Args:
        topic: search query (required)
        sources: comma-separated subset — "projects,bookmarks,tg,palace,all"
        days: optional time-window filter

    Returns:
        dict with 'summary' (markdown) + per-source counts.
    """
    if not topic or not topic.strip():
        return {
            "summary": "_Empty topic — provide a query to surface relevant content._",
            "counts": {},
            "topic": topic,
        }

    enabled = {s.strip() for s in (sources or "all").lower().split(",")}
    use_all = "all" in enabled or not enabled

    proj_matches = []
    bookmark_matches = []
    tg_matches = []
    palace_matches = []

    if use_all or "projects" in enabled:
        proj_matches = projects_src.search(query=topic, days=days)

    if use_all or "bookmarks" in enabled:
        bookmark_matches = bookmarks_src.search(query=topic, days=days)

    if use_all or "tg" in enabled:
        tg_matches = tg_src.search(query=topic, days=days)

    if use_all or "palace" in enabled:
        palace_matches = _query_mempalace_search(topic=topic)

    # Build markdown
    parts = [f"# 🔍 Surface: `{topic}`\n"]
    if days:
        parts.append(f"_Time window: last {days} days_\n")

    parts.append(_format_palace_matches(palace_matches))
    parts.append(_format_project_matches(proj_matches))
    parts.append(_format_bookmark_matches(bookmark_matches))
    parts.append(_format_tg_matches(tg_matches))

    summary_md = "\n".join(p for p in parts if p)

    if not (proj_matches or bookmark_matches or tg_matches or palace_matches):
        summary_md = (
            f"# 🔍 Surface: `{topic}`\n\n"
            f"Ничего не найдено по этому topic в сканируемых источниках.\n\n"
            f"_Sources checked: projects, bookmarks, tg saved, palace drawers._"
        )

    return {
        "summary": summary_md,
        "counts": {
            "projects": len(proj_matches),
            "bookmarks": len(bookmark_matches),
            "tg_saved": len(tg_matches),
            "palace_drawers": len(palace_matches),
        },
        "topic": topic,
        "days": days,
    }
