# Launch Content Drafts — PolyPalace v0.1

Ready to copy-paste / edit and post on Sunday.

---

## Twitter / X thread (7 tweets)

**1/7**

🧵 I built **PolyPalace** — ask Claude "Шо слышно?" (what's new?) and it synthesizes everything that happened across your projects this week.

[GIF of demo here]

100% local. No cloud. MIT.

→ github.com/extezzu/polypalace

**2/7**

Why?

Every Claude session starts fresh. You bookmark research, dump ideas in Telegram, work across multiple projects — and Claude knows none of it.

PolyPalace fixes that with one question: "what's new?"

**3/7**

How it works:

It's a **fork of MemPalace** (96.6% R@5 LongMemEval, ChromaDB-backed) — so you get 29 memory tools out of the box.

PolyPalace adds 2 synthesis tools that reach **beyond** the palace:
- `whats_new` — composite recent activity
- `surface_ideas` — topic-specific recall

**4/7**

Sources synthesized:

📁 Multi-project folder (`~/Desktop/projects/*`)
🔖 Brave bookmarks (recent)
💬 Telegram Saved Messages (export)
🧠 MemPalace drawers (memory)

All filtered, formatted, returned as Markdown for Claude.

**5/7**

Privacy:

→ Runs **fully locally** via stdio
→ No cloud calls, no telemetry
→ Per-project `.mcpignore` for fenced projects
→ Built-in skip pattern for sensitive folder names

Your data never leaves your laptop.

**6/7**

Install:

```bash
pip install polypalace
```

Add to Claude Desktop config:
```json
{"mcpServers": {"polypalace": {"command": "polypalace-mcp"}}}
```

Restart Claude. Ask "Шо слышно?". Done.

**7/7**

Built this in one weekend on top of @MemPalaceMCP's MIT-licensed work.

If you use Claude Desktop with multiple projects + bookmarks + saved-messages chaos like me, this might save you time too.

⭐ on GitHub: github.com/extezzu/polypalace

---

## LinkedIn post (longer-form)

**Title**: I built a Claude Desktop assistant that knows what I did this week

This weekend I shipped PolyPalace — a Model Context Protocol (MCP) server for Claude Desktop that synthesizes activity across multiple data sources I care about.

**The problem**

Every time I start a new Claude Desktop session, it knows nothing about:
- What I worked on across my multiple projects
- Articles I bookmarked in Brave during research
- Random ideas I dump into Telegram Saved Messages
- Past decisions stored in conversation history

I'd repeatedly find myself re-explaining context. Annoying.

**The solution**

PolyPalace adds two MCP tools to Claude Desktop:

1. `whats_new` — Ask "Шо слышно?" (Russian/Ukrainian for "what's new?") and Claude returns a Markdown synthesis of everything that happened across your projects in the last N days, including bookmarks added, TG saved items, and memory-layer drawers.

2. `surface_ideas` — Topic-specific recall. Search across all sources for "what did I save about X?"

**Why it's a fork, not a clone**

PolyPalace is built on top of MemPalace (https://github.com/MemPalace/mempalace), an excellent MIT-licensed personal memory MCP. MemPalace gives you 29 memory tools out of the box (drawers, diary, knowledge graph, semantic search via ChromaDB, 96.6% R@5 on LongMemEval). PolyPalace adds 2 synthesis tools on top.

Reusing > reinventing. Acknowledged in README, license preserved.

**Tech**

- Python 3.9+
- ChromaDB for vector search (inherited)
- Pure-function source readers (projects/bookmarks/tg)
- 100% local, no cloud calls
- MIT licensed

**Installation**

`pip install polypalace` → add to Claude Desktop config → ask "Шо слышно?"

GitHub: https://github.com/extezzu/polypalace

If you use Claude Desktop with multiple projects, this might save you time. PRs welcome.

---

## Hacker News title (Show HN)

**Show HN: PolyPalace – Ask Claude Desktop 'what's new' across all your projects, fully local**

Body:

I forked MemPalace (MIT, 96.6% R@5 on LongMemEval) and added two synthesis tools on top: `whats_new` (composite recent activity across projects + bookmarks + TG saved messages + palace drawers) and `surface_ideas` (topic-specific recall).

Trigger phrase is conversational: "Шо слышно?" (Russian/Ukrainian "what's new?"). Returns Markdown summary of everything that changed in the last week across your laptop's project folders, your Brave bookmarks, your Telegram Saved Messages export, and your MemPalace memory.

Runs fully locally over stdio. Privacy-first: drop a `.mcpignore` in any project folder and it gets fully fenced. Built-in skip pattern for sensitive project names.

Built in one weekend. Open to feedback, PRs especially welcome for new source adapters (Notion, Chrome, etc.).

GitHub: https://github.com/extezzu/polypalace
Upstream attribution: https://github.com/MemPalace/mempalace

---

## Reddit r/ClaudeAI post

**Title**: Built a Claude Desktop assistant that synthesizes "what I did this week" across projects + bookmarks + Telegram saves

**Body**:

I work across multiple projects on my laptop and was getting tired of every Claude Desktop session starting fresh with zero context about what I'd done recently. So I built PolyPalace — a fork of MemPalace with two synthesis tools added on top.

Ask Claude "Шо слышно?" and it returns:
- 📁 Recent activity in `~/Desktop/projects/*` (skips configured projects)
- 🔖 Bookmarks added in Brave
- 💬 Telegram Saved Messages from export
- 🧠 MemPalace drawers (memory layer)

All composed as Markdown for Claude.

Built on MemPalace (MIT, 96.6% R@5 LongMemEval) — credit where due. PolyPalace adds the synthesis layer; MemPalace handles the memory.

GitHub: https://github.com/extezzu/polypalace

Anyone else dealing with multi-source context fragmentation in Claude Desktop? Curious what other sources would be useful — currently thinking Notion, Apple Notes (macOS), Slack DMs.

---

## PulseMCP / Smithery directory description

**Short (140 chars)**:
Personal AI assistant for Claude Desktop. Synthesizes activity across projects, Brave bookmarks, Telegram saves, and memory layer.

**Long (500 chars)**:
PolyPalace is a fork of MemPalace that adds two synthesis tools: `whats_new` (composite recent-activity across multi-project folders + Brave bookmarks + Telegram saved messages + memory drawers) and `surface_ideas` (topic-specific recall). Trigger "Шо слышно?" and Claude tells you what changed this week. 100% local via stdio, no cloud calls, no telemetry. Built on MemPalace's 96.6% R@5 LongMemEval-tested foundation. MIT licensed. Per-project `.mcpignore` for fenced projects.

---

## Loom / Demo Video Script (~90 seconds)

**0:00–0:10** (Hook)
"Hey, I'm Dmytro. I built a Claude Desktop assistant that knows what I did this week across all my projects. It's free, MIT, and runs fully locally."

**0:10–0:30** (Killer demo)
Open Claude Desktop. Type: "Шо слышно?"
[Show response: Markdown with projects, bookmarks, TG, palace sections]
"That's everything I did this week across all my data sources. One question, real answer."

**0:30–0:50** (Second demo)
Type: "Surface my notes on MCP servers"
[Show surface_ideas response: relevant project files + bookmarks + TG]
"This finds anything I previously saved about a topic — across project files, Brave bookmarks, Telegram saved messages, and the memory layer."

**0:50–1:10** (Install)
"Install in one command: `pip install polypalace`. Add three lines to your Claude Desktop config. That's it."
[Show config snippet on screen]

**1:10–1:25** (Privacy + attribution)
"Everything runs locally. No cloud, no telemetry. It's a fork of MemPalace — credit to milla-jovovich for the foundation. I added two synthesis tools."

**1:25–1:30** (Outro)
"Link in description. PRs welcome. Thanks for watching."

---

## Demo recording checklist (Sunday)

- [ ] Make TG export ready first (so demo includes TG sources)
- [ ] Have at least 1 project with recent activity (money project ✓)
- [ ] Have Brave bookmarks with recent additions (✓ — 6 found)
- [ ] Have MemPalace already initialized with some drawers (✓ — multiple drawers from session)
- [ ] Test the demo phrase end-to-end before recording
- [ ] Use OBS or Loom (no music, mic check)
- [ ] Edit out any verification codes / PII visible on screen
- [ ] Caption optional but improves engagement
