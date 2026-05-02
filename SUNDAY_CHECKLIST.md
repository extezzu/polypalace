# Sunday Finish Checklist — PolyPalace v0.1 Launch

> **🟢 STATUS UPDATE 2026-05-02 22:35** — autonomous overnight pushed everything publishable to live state:
> - GitHub repo: https://github.com/extezzu/polypalace ✅ live, public
> - Topics + description set ✅
> - v0.1.0 release published: https://github.com/extezzu/polypalace/releases/tag/v0.1.0 ✅
> - Code: 4f3db42 + tag v0.1.0 pushed ✅
> - Claude Code MCP config: mempalace → polypalace ✅
>
> **Sunday = TWO things only**: (1) restart Claude Code (one-time), (2) post social/Loom whenever you want. The rest is done.

## ⚠️ One conflict to resolve before launch

You currently have BOTH `mempalace` (upstream, in `Roaming/Python311`) AND `polypalace` (our fork, in `Local/Programs/Python311`) installed. They claim the same internal namespace (`mempalace.*`). Python path priority makes the OLD one load.

**Fix**: uninstall old `mempalace`, then `pip install -e .` polypalace. Script handles it (see below).

**Pre-fix requirement**: **Quit Claude Desktop fully** (right-click tray icon → Quit). Otherwise `mempalace-mcp.exe` is file-locked and uninstall fails.

---

## 🟢 Activation (3 commands, ~30 sec)

```powershell
# 1. Quit Claude Desktop fully (right-click tray → Quit) — required to release file lock
# 2. Run uninstall + reinstall:

cd c:\Users\Bruger\Desktop\projects\personal-cto-mcp
pip uninstall -y mempalace
pip install -e .
```

After this, the path conflict is resolved. Restart Claude Code (close VS Code → reopen) and `polypalace` MCP will serve all 31 tools (29 MemPalace + 2 PolyPalace synthesis).

### Verify (optional)

```powershell
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | polypalace-mcp 2>$null | python -c "import json,sys; d=json.load(sys.stdin); names=[t['name'] for t in d['result']['tools']]; print(f'{len(names)} tools'); print('whats_new:', 'whats_new' in names); print('surface_ideas:', 'surface_ideas' in names)"
```

Expected: `31 tools / whats_new: True / surface_ideas: True`

---

## 🟡 Optional — content + distribution (whenever)

Не блокеры publish. Каждое можно делать в любой момент week / Monday / next weekend.

### TG Desktop export (10 min, optional)

Required ONLY if you want TG Saved messages in synthesis output. Without it, `whats_new` shows other sources fine, just no TG section.

1. Telegram Desktop → Settings → Advanced → **Export Telegram Data**
2. Uncheck everything except **Saved Messages**
3. Format: **JSON**
4. Save to `c:\Users\Bruger\Desktop\tg-export\`
5. Verify `Desktop\tg-export\result.json` exists

### Update Claude Desktop config (5 min)

After Claude Desktop quit + restart с polypalace:

Edit `%APPDATA%\Claude\claude_desktop_config.json`:

Find existing `mempalace` entry, replace with:
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

Restart Claude Desktop. Test: ask Claude **"Use polypalace whats_new tool to show last 7 days"**.

### Loom recording (~60 min, optional)

Script in `LAUNCH_POSTS.md` → "Loom / Demo Video Script". ~90 sec target.

Get TG export done first if you want TG content shown в demo.

### Social posts (~30 min, optional)

Drafts in `LAUNCH_POSTS.md`:
- Twitter thread (7 tweets)
- LinkedIn post
- Hacker News Show HN
- Reddit r/ClaudeAI

Post in any order. Replace `[GIF placeholder]` с Loom URL or static screenshot.

### Directory submits (~15 min)

- PulseMCP: https://www.pulsemcp.com/submit
- Smithery: https://smithery.ai/submit
- awesome-mcp GitHub list — open PR

### PyPI publish (15 min, optional)

```bash
pip install build twine
python -m build
twine upload dist/*
# username: __token__
# password: pypi-...your-token...
```

Skip if you don't want public package now. GitHub clone install works fine without PyPI.

---

## 📋 Decision flowchart

```
Want zero Sunday?
└── YES → skip everything, code waits в local commit
└── NO  → 5-min minimum launch:
          ├── Run launch.ps1 (or manual steps)
          └── done — repo public

After publish, on YOUR schedule:
├── Loom recording (whenever you have daylight + clean shirt)
├── Social posts (whenever traffic patterns are good)
├── PyPI publish (whenever or never)
```

---

## 🔥 Troubleshooting

**"file lock" / "permission denied" on uninstall**
→ Claude Desktop is running. Quit fully from tray icon.

**"polypalace-mcp not found"**
→ pip install -e . did not finish. Re-run.

**MCP server returns 29 tools instead of 31**
→ Old mempalace still loading. Verify `python -c "import mempalace; print(mempalace.__file__)"` shows path containing `personal-cto-mcp`.

**Repo creation fails: "name already exists"**
→ Already created earlier. Just `git push origin develop`.

**MCP server hangs on Claude Desktop**
→ Check `%APPDATA%\Claude\logs\` for error trace. Often: missing `chromadb` or env var.

---

## 🛑 If you change mind

Don't run launch.ps1. Local commits stay on your machine. No upload, no publication. Decision reversible at any time.

---

**Last updated**: 2026-05-02 22:25 (autonomous)
