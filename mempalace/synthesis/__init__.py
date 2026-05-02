"""
synthesis — multi-project knowledge synthesis tools added on top of MemPalace.

New MCP tools:
- whats_new      : composite recent activity across projects + bookmarks + TG + palace drawers
- surface_ideas  : surface relevant ideas from sources for current topic context

Sources:
- mempalace.synthesis.sources.projects       — multi-project folder scanner
- mempalace.synthesis.sources.bookmarks      — Brave Bookmarks JSON reader
- mempalace.synthesis.sources.tg_export      — Telegram Desktop export reader

Architecture:
- All sources are pure-function readers — no side effects, no state
- Each source returns list[dict] with shape: {source, date, title, content, path, project?}
- Tools compose source outputs into structured Markdown synthesis
"""

from . import sources  # noqa: F401
