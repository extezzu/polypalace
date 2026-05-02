"""
projects — multi-project folder scanner.

Reads `<projects_root>/<project_name>/` directory and returns recent activity.

Configuration:
- PROJECTS_ROOT env var or default `~/Desktop/projects`
- Skip pattern: any project name matching `^attack/i` (case-insensitive prefix "attack")
- Skip mechanism: any project containing `.mcpignore` file at root
- Hardcoded skip dirs: node_modules, .git, dist, build, target, .next, .venv, __pycache__, .vault

Output shape per item:
{
    "source": "project",
    "project": str,           # project name (folder name)
    "path": str,              # absolute path
    "date": str,              # ISO 8601 date of last modification
    "title": str,             # heading or filename
    "content": str,           # snippet (first 500 chars)
}
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Iterator


# Default project root (override via env var)
DEFAULT_ROOT = Path.home() / "Desktop" / "projects"

# Skip rules
# Match BOTH Latin "Attack" AND Cyrillic "Аттак" prefix (user used both spellings)
SKIP_PROJECT_PATTERN = re.compile(r"^(attack|аттак)", re.IGNORECASE)
SKIP_PROJECT_NAMES = {"_tmp", "_temp_extezzu"}  # known temp/scratch dirs
SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", "target",
    ".next", ".venv", "venv", "__pycache__", ".vault",
    ".mempalace", ".idea", ".vscode", "tool-results",
}
SKIP_EXTS = {".pyc", ".log", ".tmp", ".lock", ".DS_Store"}

# Files we consider primary knowledge content
PRIMARY_FILES = {
    "CLAUDE.md", "RESUME.md", "MEMORY.md", "README.md",
    "WEALTH_PLAN.md", "MASTER_PLAN.md",
}

# Subdirs we recursively scan (relative to project root)
SCAN_SUBDIRS = [
    "wealth/sessions",
    "data/research",
    "applications",
    "profile",
    "sessions",
    "notes",
    "docs",
]


def _get_root() -> Path:
    """Resolve projects root, honoring env override."""
    override = os.environ.get("PERSONAL_CTO_MCP_PROJECTS_ROOT")
    if override:
        return Path(override).expanduser()
    return DEFAULT_ROOT


def _should_skip_project(name: str, project_path: Path) -> bool:
    """True if project should be excluded from scans."""
    if name in SKIP_PROJECT_NAMES:
        return True
    if SKIP_PROJECT_PATTERN.match(name):
        return True
    if (project_path / ".mcpignore").exists():
        return True
    return False


def _list_projects(root: Path) -> list[Path]:
    """List candidate project directories under root."""
    if not root.exists():
        return []
    out = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        if _should_skip_project(child.name, child):
            continue
        out.append(child)
    return out


def _file_mtime_iso(p: Path) -> str:
    """Return ISO 8601 mtime."""
    try:
        ts = p.stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except OSError:
        return ""


def _read_snippet(p: Path, max_chars: int = 500) -> str:
    """Read first N chars of a text file safely."""
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(max_chars)
    except OSError:
        return ""


def _extract_title(content: str, fallback: str) -> str:
    """Extract first H1/H2 from markdown, else use fallback."""
    for line in content.splitlines()[:20]:
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
        if s.startswith("## "):
            return s[3:].strip()
    return fallback


def _walk_files(project_path: Path) -> Iterator[Path]:
    """Walk project, yielding text files of interest."""
    # Top-level primary files
    for name in PRIMARY_FILES:
        p = project_path / name
        if p.exists() and p.is_file():
            yield p

    # Recurse into select subdirs
    for sub in SCAN_SUBDIRS:
        d = project_path / sub
        if not d.exists() or not d.is_dir():
            continue
        for root, dirs, files in os.walk(d):
            # Prune skipped dirs in-place
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith(".")]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in SKIP_EXTS:
                    continue
                # Only text-like files
                if ext in {".md", ".txt", ".rst", ""} or not ext:
                    yield Path(root) / f


def list_projects() -> list[dict]:
    """Return summary of all (non-skipped) projects."""
    root = _get_root()
    projects = _list_projects(root)
    out = []
    for p in projects:
        out.append({
            "name": p.name,
            "path": str(p),
            "last_modified": _file_mtime_iso(p),
        })
    return out


def recent_activity(days: int = 7, project: str | None = None) -> list[dict]:
    """
    Scan all (or one) project for files modified in the last N days.

    Args:
        days: lookback window
        project: limit to this project name (optional)

    Returns:
        list of dicts (sorted by date DESC) — see module docstring for shape
    """
    root = _get_root()
    cutoff_ts = time.time() - (days * 86400)

    projects = _list_projects(root)
    if project:
        projects = [p for p in projects if p.name == project]

    items = []
    for proj in projects:
        for f in _walk_files(proj):
            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue
            if mtime < cutoff_ts:
                continue
            content = _read_snippet(f, 500)
            title = _extract_title(content, f.name)
            try:
                rel = f.relative_to(proj)
            except ValueError:
                rel = f.name
            items.append({
                "source": "project",
                "project": proj.name,
                "path": str(f),
                "rel_path": str(rel),
                "date": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
                "title": title,
                "content": content[:300],  # tighter for synthesis
            })

    items.sort(key=lambda x: x["date"], reverse=True)
    return items


def search(query: str, days: int | None = None, project: str | None = None) -> list[dict]:
    """
    Simple keyword search across project files.

    Args:
        query: search term (case-insensitive substring)
        days: optional time filter
        project: optional project filter

    Returns:
        list of matching items (best-effort scoring)
    """
    if not query or not query.strip():
        return []
    q_low = query.lower().strip()

    root = _get_root()
    projects = _list_projects(root)
    if project:
        projects = [p for p in projects if p.name == project]

    cutoff_ts = (time.time() - days * 86400) if days else 0.0

    items = []
    for proj in projects:
        for f in _walk_files(proj):
            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue
            if cutoff_ts and mtime < cutoff_ts:
                continue
            try:
                with open(f, "r", encoding="utf-8", errors="ignore") as fp:
                    full = fp.read()
            except OSError:
                continue
            full_low = full.lower()
            if q_low not in full_low:
                continue

            # Simple score: occurrence count + recency boost
            occurrences = full_low.count(q_low)
            recency_factor = 1.0 + max(0.0, (mtime - (time.time() - 30 * 86400)) / (30 * 86400))
            score = occurrences * recency_factor

            # Extract snippet around first match
            idx = full_low.find(q_low)
            start = max(0, idx - 100)
            end = min(len(full), idx + 200)
            snippet = full[start:end].strip()

            try:
                rel = f.relative_to(proj)
            except ValueError:
                rel = f.name
            items.append({
                "source": "project",
                "project": proj.name,
                "path": str(f),
                "rel_path": str(rel),
                "date": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
                "title": _extract_title(full[:1000], f.name),
                "content": snippet,
                "score": round(score, 2),
            })

    items.sort(key=lambda x: x["score"], reverse=True)
    return items[:20]  # top-20
