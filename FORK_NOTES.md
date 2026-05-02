# Fork Notes — PolyPalace

This is a **fork of [MemPalace](https://github.com/MemPalace/mempalace)** (MIT-licensed) extended with multi-project synthesis tools.

## Why fork

MemPalace is best-in-class personal AI memory (96.6% R@5 on LongMemEval, ChromaDB-backed, 29 MCP tools). We add 2 synthesis tools on top that reach **beyond** the palace into multi-project folders, Brave bookmarks, and Telegram Saved Messages.

Goal: single-distribution personal AI assistant that combines memory layer with cross-source synthesis.

## What's added

Compared to upstream MemPalace, this fork adds:

- `mempalace/synthesis/` — new module
  - `sources/projects.py` — multi-project folder scanner
  - `sources/bookmarks.py` — Brave bookmarks JSON reader
  - `sources/tg_export.py` — Telegram Desktop export reader
  - `whats_new.py` — composite recent-activity synthesis tool
  - `surface_ideas.py` — topic-specific recall across sources

Modified files:
- `mempalace/mcp_server.py` — registered 2 new tools (`whats_new`, `surface_ideas`) in TOOLS dict, added imports

## New tools

### `whats_new`
Composite recent-activity synthesis. Trigger phrase: **"Шо слышно?"** / **"What's new?"**

Reads:
1. All projects in `~/Desktop/projects/*` (skip `Attack!`/`Аттак!` and `.mcpignore` projects)
2. Brave bookmarks added recently
3. Telegram Saved Messages from export
4. MemPalace drawers (graceful fallback if palace unavailable)

Returns Markdown summary grouped by source.

### `surface_ideas`
Topic-specific recall. Search across sources for content matching a topic.

Different from `whats_new` (recent activity) — this is "what did I save about X" recall.

## Configuration

Environment variables:

- `PERSONAL_CTO_MCP_PROJECTS_ROOT` — override projects folder (default: `~/Desktop/projects`)
- `PERSONAL_CTO_MCP_BOOKMARKS_PATH` — override Brave bookmarks file path (auto-detected per OS)
- `PERSONAL_CTO_MCP_TG_EXPORT_PATH` — override TG export JSON path (default: `~/Desktop/tg-export/result.json`)

Per-project ignore: place a `.mcpignore` file at project root → entire project skipped.

Pattern skip: any project whose name starts with `Attack` (Latin) or `Аттак` (Cyrillic), case-insensitive, is automatically ignored.

## Setup TG export

1. Telegram Desktop → Settings → Advanced → Export Telegram Data
2. Select **Saved Messages only**
3. Format: **JSON**
4. Save to `~/Desktop/tg-export/result.json` (or override via env var)
5. Re-export periodically (e.g., weekly) to keep data fresh

## Attribution

- Upstream: [MemPalace](https://github.com/MemPalace/mempalace) by milla-jovovich, MIT License
- Fork: Personal CTO MCP, MIT License (preserves upstream license)

## TODO before publish

- [ ] Pick final fork name (working name: `personal-cto-mcp`)
- [ ] Update `pyproject.toml` — name, version 0.1.0, description, scripts
- [ ] Update top-level README with fork-specific intro + demo GIF
- [ ] Set up GitHub repo
- [ ] Test full MCP server boot via `npx @modelcontextprotocol/inspector`
- [ ] Record Loom demo (~90s, "Шо слышно?" demo)
- [ ] Write Twitter thread + LinkedIn + HN Show post
- [ ] Submit to PulseMCP + Smithery directories

## Verified working (live test 2026-05-02 22:30)

- ✅ Project scanner: detected 8 projects in `~/Desktop/projects/`, 22 recently-modified files
- ✅ Bookmarks reader: 6 bookmarks parsed from Brave (Default profile)
- ✅ `whats_new(days=7)`: composite Markdown output formatted correctly
- ✅ `surface_ideas("MCP server")`: 11 project files matched with relevant snippets
- ✅ Skip patterns: `Аттак`/`Attack` + `_tmp`/`_temp_extezzu` correctly excluded
- ⏸ TG export: not yet configured (user task — export Saved Messages from TG Desktop)
- ⏸ Palace integration: tested fallback path (palace not init in test env, gracefully empty)
