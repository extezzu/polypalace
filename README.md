# PolyPalace

> Personal AI assistant for Claude Desktop — synthesizes activity across your multi-project folder, Brave bookmarks, Telegram saved messages, and a memory layer. Ask Claude **"Шо слышно?"** ("what's new?") and get a real answer.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io)

> **Fork notice**: PolyPalace is a fork of [MemPalace](https://github.com/MemPalace/mempalace) (MIT licensed). It preserves all 29 MemPalace memory tools and adds 2 synthesis tools on top. See [Attribution](#attribution).

## What it does

You have multiple projects on your laptop. You bookmark research links. You dump random ideas into Telegram Saved Messages. You also have a long history of conversations with Claude.

**PolyPalace asks Claude to make sense of all that, on demand.**

```
You: Шо слышно?

Claude (via PolyPalace):
  📁 Projects activity (last 7 days)
    money:
      - Submitted Freelancer.com KYC (May 2)
      - Updated WEALTH_PLAN.md (5-phase ownership pivot)
      - 4 new files in data/research/
    artificial-brain:
      - (stale 14 days)

  🔖 Bookmarks added
    - "MCP server tutorial" (modelcontextprotocol.io)
    - "Anthropic Partner Network" (anthropic.com)

  💬 Telegram Saved highlights
    - "idea: Telegram bot that…" (May 1)

  🧠 Palace drawers (recent)
    - [money/planning] WEALTH_PLAN ownership pivot…
```

## Why fork MemPalace?

[MemPalace](https://github.com/MemPalace/mempalace) is best-in-class personal AI memory: 96.6% R@5 on LongMemEval, ChromaDB-backed, 29 MCP tools, MIT licensed. PolyPalace adds **2 synthesis tools** that reach beyond the palace into multi-project folders + Brave bookmarks + Telegram exports.

If you only need conversation memory, use upstream MemPalace. If you want a personal assistant that knows about your laptop's project structure and surfaces relevant past saves automatically — use PolyPalace.

## Install

```bash
pip install polypalace
polypalace init ~/Desktop/projects/your-main-project
```

Or clone and install in dev mode:

```bash
git clone https://github.com/extezzu/polypalace.git
cd polypalace
pip install -e .
```

## Configure Claude Desktop

Add to `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "polypalace": {
      "command": "polypalace-mcp",
      "args": []
    }
  }
}
```

Restart Claude Desktop.

## New tools (vs MemPalace)

### `whats_new`
Composite recent-activity synthesis across all sources.

**Trigger phrases**: "Шо слышно?" / "What's new?" / "what happened this week?"

**Inputs**:
- `days` (default 7): lookback window
- `focus` (optional): project name OR topic keyword

### `surface_ideas`
Topic-specific recall across sources. Different from `whats_new` — this answers "what did I save about X?" rather than "what happened recently?"

**Inputs**:
- `topic` (required): search query
- `sources` (optional): comma-separated subset — `projects`, `bookmarks`, `tg`, `palace`, `all`
- `days` (optional): time window

Plus all 29 MemPalace memory tools (drawers, diary, knowledge graph, semantic search, etc.).

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `PERSONAL_CTO_MCP_PROJECTS_ROOT` | `~/Desktop/projects` | Root folder containing your projects |
| `PERSONAL_CTO_MCP_BOOKMARKS_PATH` | auto-detect Brave path | Override bookmarks file path |
| `PERSONAL_CTO_MCP_TG_EXPORT_PATH` | `~/Desktop/tg-export/result.json` | TG Desktop export JSON |

## Privacy

**Everything runs locally.** Zero cloud calls. No telemetry. Your data never leaves your laptop.

### Skip rules (built in)

- Project name matches `^attack` (Latin) or `^аттак` (Cyrillic), case-insensitive → fully skipped
- Project root contains `.mcpignore` file → fully skipped
- Hardcoded skip dirs in walks: `node_modules`, `.git`, `dist`, `build`, `__pycache__`, `.venv`, etc.

### Per-project ignore

Drop a `.mcpignore` file (any content) at a project root → that entire project is invisible to PolyPalace synthesis tools. Use for sensitive projects you want fully fenced.

## Setting up Telegram export

1. Telegram Desktop → **Settings** → **Advanced** → **Export Telegram Data**
2. Select **Saved Messages only**, format **JSON**
3. Save to `~/Desktop/tg-export/result.json` (or override via env var)
4. Re-export periodically to keep PolyPalace's view fresh

(Live MTProto access is out of scope for now — static export is the supported path.)

## Setting up Brave bookmarks

PolyPalace auto-detects Brave's bookmarks file. If Brave is running while PolyPalace reads bookmarks, the file may be locked — PolyPalace copies the file to a temp snapshot first to avoid this.

If you use a non-default Brave profile or want Chrome instead, set `PERSONAL_CTO_MCP_BOOKMARKS_PATH` to point at the right `Bookmarks` JSON file.

## Examples

### "What did I do this week?"

```
> Шо слышно?

[Composite synthesis returns Markdown across all sources]
```

### "What was I researching about MCP?"

```
> Surface my notes on MCP servers

[surface_ideas("MCP servers") returns project files + bookmarks + TG snippets + palace drawers matching topic]
```

### Filter to one project

```
> Шо слышно in money project last 14 days?

[whats_new(days=14, focus="money")]
```

## Attribution

**Upstream**: [MemPalace](https://github.com/MemPalace/mempalace) by milla-jovovich, MIT License. We preserve their license, mining engine, knowledge graph, ChromaDB backend, and all 29 memory tools as-is. The original upstream README is preserved at [README.upstream.md](README.upstream.md).

**Fork additions** (PolyPalace, 2026-05): `mempalace/synthesis/` module with `whats_new` and `surface_ideas` tools and 3 source readers (projects, bookmarks, tg_export). MIT License.

## Roadmap

**v0.1** (current)
- ✅ `whats_new` composite synthesis
- ✅ `surface_ideas` topic recall
- ✅ Multi-project + Brave + TG export sources
- ✅ MemPalace integration (palace drawers in synthesis)

**v0.2** (next)
- Live Telegram MTProto access (replace static export)
- Chrome / Firefox / Edge bookmark support
- Notion API source
- `cross_project_insight` tool (pattern transfer)

**v0.3** (later)
- `idea_capture` write tool
- Real-time file watching
- Cross-platform binary releases

## License

MIT — see [LICENSE](LICENSE).

## Contributing

PRs welcome. New source adapters especially — drop them in `mempalace/synthesis/sources/` following the existing pattern (pure functions, dict outputs with `source/date/title/content` shape).
