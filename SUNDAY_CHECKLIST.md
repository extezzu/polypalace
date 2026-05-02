# Sunday Finish Checklist — PolyPalace v0.1

> **STATUS 2026-05-02 22:50** — Fully published. User decisions applied:
> - GitHub repo LIVE: https://github.com/extezzu/polypalace
> - v0.1.0 release: https://github.com/extezzu/polypalace/releases/tag/v0.1.0
> - Code: 464785e (after privacy fix — author email rewritten to GitHub noreply)
> - Claude Code MCP config: mempalace → polypalace ✅
> - Project hooks: `mempalace hook run` → `polypalace hook run` ✅
>
> **CANCELLED per user**: Loom recording, Twitter/LinkedIn/HN/Reddit posts, PulseMCP/Smithery submits.
>
> **Sunday = ZERO mandatory + 1 optional activation step.** Even that can be skipped — code is live на GitHub for anyone who wants to clone.

## 🟢 Optional activation (3 commands, ~30 sec) — ONLY needed if you want polypalace tools active in your Claude Code

```powershell
# 1. Quit Claude Desktop fully (right-click tray → Quit) — releases file lock
# 2. Run:
cd c:\Users\Bruger\Desktop\projects\personal-cto-mcp
pip uninstall -y mempalace
pip install -e .
# 3. Restart VS Code + Claude Code
```

After: `polypalace` MCP serves all 31 tools (29 MemPalace + 2 PolyPalace synthesis: `whats_new`, `surface_ideas`).

### Verify (optional)

```powershell
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | polypalace-mcp 2>$null | python -c "import json,sys; d=json.load(sys.stdin); names=[t['name'] for t in d['result']['tools']]; print(f'{len(names)} tools'); print('whats_new:', 'whats_new' in names); print('surface_ideas:', 'surface_ideas' in names)"
```

Expected: `31 tools / whats_new: True / surface_ideas: True`

## 🟡 v0.2 — TG live access (deferred, planned)

User wants automatic TG Saved Messages reading without manual export. Static export approach (current v0.1) requires manual re-export.

**v0.2 plan** (separate weekend task):
- Use `telethon` MTProto library
- User obtains `api_id` + `api_hash` from https://my.telegram.org once
- First-time login: phone code via SMS (one-time)
- Session file saved locally → auto-auth thereafter
- All credentials in `.env` (gitignored)
- Session file in `.tg-session/` (gitignored)
- New tool: `tg_recent` — replaces static export with live API call

**Critical**: credentials NEVER committed. `.env` and session files added to `.gitignore` already (upstream). Will add explicit comments in v0.2 docs.

## 🛑 Not doing (per user)

- ~~Loom recording~~ — cancelled
- ~~Twitter / LinkedIn / HN / Reddit posts~~ — cancelled
- ~~PulseMCP / Smithery directory submits~~ — no logins there
- ~~PyPI publish~~ — `pip install` from git clone works, sufficient

## 🔥 Troubleshooting

- **"file lock" / "permission denied"** on uninstall → Claude Desktop running. Quit fully from tray.
- **`polypalace-mcp` not found** → pip install -e . did not finish. Re-run.
- **MCP returns 29 tools instead of 31** → Old mempalace still loading. Verify path: `python -c "import mempalace; print(mempalace.__file__)"` should show `personal-cto-mcp`.
- **MCP server hangs** → check `%APPDATA%\Claude\logs\` for trace.

## 📋 Security audit results (2026-05-02)

Verified across all extezzu repos via GitHub Code Search API:
- ✅ No PII leaks (email, CPR, bank account, driver license, address)
- ✅ No API keys in public code
- ✅ All `sk-ant-`, `PRIVATE KEY`, `OPENAI_API_KEY` matches are regex patterns or env var references
- ✅ All hits in private `agrirate` repo are variable name references, not actual values
- ✅ Author email rewritten to `extezzu@users.noreply.github.com` in polypalace commits

## ✅ TL;DR

**Code is live на GitHub.** Sunday optional: 3 commands + restart to activate locally. Or skip entirely — code waits on GitHub forever, no urgency.

---

**Last updated**: 2026-05-02 22:55
