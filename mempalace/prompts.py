"""
PolyPalace MCP Prompts Module
==============================

Implements the MCP `prompts/list`, `prompts/get`, and `completion/complete`
handlers for PolyPalace. Designed to drop into the existing hand-rolled
JSON-RPC server in `mempalace/mcp_server.py` (which does NOT use the Python
MCP SDK — it builds protocol-compliant dicts directly), so this module
follows the same convention: every value is a plain dict matching the
MCP 2025-11-25 wire format.

Reference:
    https://modelcontextprotocol.io/specification/2025-11-25/server/prompts

Eight slash-command-style prompts are exposed:

    /recall <topic>            → search across drawers + diary + KG
    /journal                   → append today's diary entry
    /state-of-mind             → recent diary trend (last N days)
    /who-knows <person>        → KG query + tunnels + drawer mentions
    /time-machine <date>       → everything from a specific date
    /connect <topic1> <topic2> → KG path between two topics
    /forget-old                → surface stale drawers
    /whats-on-my-mind          → auto-summary of recent KG additions

Each `get_prompt` returns a sequence of MCP `PromptMessage` dicts. Two
patterns are used depending on the prompt:

  1. **Direct execution prompts** (e.g. /journal) — the assistant message
     contains an explicit instruction to call a single tool with
     pre-filled arguments, leaving no ambiguity for the client LLM.

  2. **Composed prompts** (e.g. /recall, /state-of-mind) — the assistant
     message lays out a numbered tool-chain, each step describing exactly
     which `mempalace_*` tool to call and with what arguments. The client
     LLM executes the chain and produces a synthesized response.

This indirection is intentional: PolyPalace exposes its capabilities as
*tools*. Prompts are user-facing entry points that orchestrate those
tools; they are deliberately thin — almost entirely text scaffolding
plus argument substitution — to keep the trust boundary clean (no shell
of work happens inside the prompt; it just instructs the LLM).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# 1. Prompt Definitions
# ---------------------------------------------------------------------------
#
# Schema for each entry mirrors the MCP wire format for `prompts/list`:
#   {
#     "name": str,
#     "title": str,                # optional human-friendly label
#     "description": str,
#     "arguments": [
#       { "name": str, "description": str, "required": bool }
#     ]
#   }
#
# Note: the MCP spec for prompt arguments uses {name, description, required}
# only — there is no JSON-schema field per argument (unlike tools). Clients
# infer types from descriptions and from `completion/complete` results.


PROMPT_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "recall",
        "title": "Recall everything about a topic",
        "description": (
            "Search the entire palace — drawers, diary entries, and the "
            "knowledge graph — for any reference to a topic. Returns a "
            "synthesised summary that pulls from every memory layer."
        ),
        "arguments": [
            {
                "name": "topic",
                "description": "What to recall (e.g. 'fiverr', 'Max', 'Q1 plan')",
                "required": True,
            }
        ],
    },
    {
        "name": "journal",
        "title": "Append a diary entry",
        "description": (
            "Write a timestamped diary entry under today's date. Optional "
            "mood tag and free-form tags are stored as topic metadata."
        ),
        "arguments": [
            {
                "name": "entry",
                "description": "The diary entry text. Free form, multi-line OK.",
                "required": True,
            },
            {
                "name": "mood",
                "description": "Mood: low | normal | high (optional)",
                "required": False,
            },
            {
                "name": "tags",
                "description": (
                    "Comma-separated tags, e.g. 'fiverr,launch,energy'. "
                    "Stored as the diary topic field."
                ),
                "required": False,
            },
        ],
    },
    {
        "name": "state-of-mind",
        "title": "Recent diary trend",
        "description": (
            "Read the last N days of diary entries and the recent knowledge-"
            "graph timeline, then summarise the period — themes, mood arc, "
            "what changed. 'Your last week in numbers'."
        ),
        "arguments": [
            {
                "name": "days",
                "description": "How many days back to look (default 7)",
                "required": False,
            }
        ],
    },
    {
        "name": "who-knows",
        "title": "Everything about a person",
        "description": (
            "Query the knowledge graph for a person, follow their tunnels "
            "to other wings/rooms, and pull every drawer that mentions "
            "them. Returns a composed bio."
        ),
        "arguments": [
            {
                "name": "person",
                "description": "Person's name as it appears in the KG (e.g. 'Max')",
                "required": True,
            }
        ],
    },
    {
        "name": "time-machine",
        "title": "Replay a specific date",
        "description": (
            "Show what was written, learned, or changed on a specific date: "
            "diary entries from that day + KG facts that became valid then "
            "+ drawers created/modified on the date."
        ),
        "arguments": [
            {
                "name": "date",
                "description": "ISO date YYYY-MM-DD (e.g. '2026-04-20')",
                "required": True,
            }
        ],
    },
    {
        "name": "connect",
        "title": "Find a path between two topics",
        "description": (
            "Search the knowledge graph for the shortest narrative chain "
            "linking two entities or topics. Returns the path plus a "
            "human-readable explanation of how they connect."
        ),
        "arguments": [
            {
                "name": "topic1",
                "description": "First entity / topic",
                "required": True,
            },
            {
                "name": "topic2",
                "description": "Second entity / topic",
                "required": True,
            },
        ],
    },
    {
        "name": "forget-old",
        "title": "Surface stale drawers",
        "description": (
            "List drawers that haven't been accessed in N days, grouped by "
            "wing. Each gets a keep / archive / delete recommendation so "
            "the user can prune memory hygiene-wise."
        ),
        "arguments": [
            {
                "name": "days",
                "description": "Staleness threshold in days (default 90)",
                "required": False,
            }
        ],
    },
    {
        "name": "whats-on-my-mind",
        "title": "Auto-summary of recent KG additions",
        "description": (
            "Pull the knowledge-graph timeline filtered to the last N hours "
            "and summarise the recurring themes. A passive 'what have I "
            "been thinking about lately' snapshot."
        ),
        "arguments": [
            {
                "name": "hours",
                "description": "Look-back window in hours (default 24)",
                "required": False,
            }
        ],
    },
]


# ---------------------------------------------------------------------------
# 2. Public handler: prompts/list
# ---------------------------------------------------------------------------


def list_prompts() -> Dict[str, Any]:
    """
    Build the response payload for an MCP `prompts/list` request.

    Returns a dict shaped like:
        { "prompts": [ {name, title, description, arguments}, ... ] }

    The caller in `mcp_server.handle_request` should wrap this dict as
    the `result` field of a JSON-RPC response.
    """
    return {"prompts": PROMPT_DEFINITIONS}


# ---------------------------------------------------------------------------
# 3. Helpers — argument validation and message construction
# ---------------------------------------------------------------------------


_AGENT_NAME = "user"
"""
The agent name passed to `mempalace_diary_write`/`mempalace_diary_read`.
PolyPalace's diary is keyed per-agent; for user-facing slash commands
we always use the literal "user". Hooks and bots use their own names.
"""


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _err(message: str, code: int = -32602) -> Dict[str, Any]:
    """JSON-RPC error envelope (caller embeds under `error`)."""
    return {"code": code, "message": message}


def _text(role: str, body: str) -> Dict[str, Any]:
    """Build a `PromptMessage` with a single text content block."""
    return {
        "role": role,
        "content": {"type": "text", "text": body},
    }


def _coerce_int(raw: Any, default: int, *, low: int = 1, high: int = 10_000) -> int:
    """Best-effort int coercion with clamp. MCP arguments arrive as strings."""
    if raw is None or raw == "":
        return default
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return default
    return max(low, min(n, high))


def _today_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# 4. Public handler: prompts/get
# ---------------------------------------------------------------------------


def get_prompt(name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Build the response payload for an MCP `prompts/get` request.

    Returns one of:
      - On success: {"description": str, "messages": [PromptMessage, ...]}
      - On error:   {"_error": {code, message}} — caller should convert
                    this into a JSON-RPC error response.

    The caller in `mcp_server.handle_request` is responsible for wrapping
    the success dict as `result` or surfacing the `_error` payload.
    """
    arguments = arguments or {}

    handler = _PROMPT_HANDLERS.get(name)
    if handler is None:
        return {"_error": _err(f"Unknown prompt: {name}", code=-32601)}
    return handler(arguments)


# ---------------------------------------------------------------------------
# 5. Per-prompt builders
# ---------------------------------------------------------------------------


def _build_recall(args: Dict[str, Any]) -> Dict[str, Any]:
    topic = (args.get("topic") or "").strip()
    if not topic:
        return {"_error": _err("`topic` is required for /recall")}

    instruction = (
        f"The user invoked the slash command `/recall {topic}`. "
        f"Pull every relevant memory layer in this exact order, then "
        f"compose a single synthesised answer. Cite drawer IDs and dates.\n\n"
        f"1. Call `mempalace_search` with arguments:\n"
        f'   {{"query": {topic!r}, "limit": 10}}\n'
        f"   This searches drawers semantically.\n\n"
        f"2. Call `mempalace_kg_query` with arguments:\n"
        f'   {{"entity": {topic!r}, "direction": "both"}}\n'
        f"   This returns typed facts about the topic.\n\n"
        f"3. Call `mempalace_diary_read` with arguments:\n"
        f'   {{"agent_name": "user", "last_n": 50}}\n'
        f"   Then filter the returned entries client-side for any whose "
        f"`content` or `topic` mentions {topic!r} (case-insensitive).\n\n"
        f"4. If `mempalace_kg_query` returned related entities, optionally "
        f"call `mempalace_find_tunnels` for the entity's wing to surface "
        f"cross-wing references.\n\n"
        f"5. Compose the final answer with three sections:\n"
        f"   - **Drawers** (semantic hits, top 5 by score)\n"
        f"   - **Knowledge graph** (typed facts, grouped by predicate)\n"
        f"   - **Diary mentions** (date-stamped, most recent first)\n"
        f"Skip any section that produced zero results."
    )
    return {
        "description": f"Recall everything about: {topic}",
        "messages": [
            _text("user", f"/recall {topic}"),
            _text("assistant", instruction),
        ],
    }


def _build_journal(args: Dict[str, Any]) -> Dict[str, Any]:
    entry = (args.get("entry") or "").strip()
    if not entry:
        return {"_error": _err("`entry` is required for /journal")}

    mood = (args.get("mood") or "").strip().lower()
    if mood and mood not in {"low", "normal", "high"}:
        return {"_error": _err("`mood` must be one of: low, normal, high")}

    tags_raw = args.get("tags") or ""
    if isinstance(tags_raw, list):
        tags = [t.strip() for t in tags_raw if str(t).strip()]
    else:
        tags = [t.strip() for t in str(tags_raw).split(",") if t.strip()]

    # Topic encodes mood + tags so the metadata stays queryable later.
    # Diary tool only takes a single `topic` string, so we synthesise one.
    topic_parts: List[str] = []
    if mood:
        topic_parts.append(f"mood:{mood}")
    topic_parts.extend(tags)
    topic = ",".join(topic_parts) if topic_parts else "general"

    today = _today_iso()
    payload = {
        "agent_name": _AGENT_NAME,
        "entry": entry,
        "topic": topic,
    }

    instruction = (
        f"The user invoked `/journal` to log a diary entry on {today}.\n\n"
        f"Call exactly one tool, then confirm:\n\n"
        f"  Tool: `mempalace_diary_write`\n"
        f"  Arguments:\n"
        f"    agent_name = {_AGENT_NAME!r}\n"
        f"    entry      = (the multi-line text below)\n"
        f"    topic      = {topic!r}\n\n"
        f"After the tool returns, reply with a one-line confirmation that "
        f"includes the returned `entry_id` and the date. Do not paraphrase "
        f"the entry back at the user; do not call any other tools."
    )

    return {
        "description": f"Journal entry for {today}",
        "messages": [
            _text(
                "user",
                "/journal\n\n"
                f"entry: {entry}\n"
                f"mood: {mood or '(unspecified)'}\n"
                f"tags: {', '.join(tags) if tags else '(none)'}",
            ),
            _text("assistant", instruction),
            # Tool input is also embedded as a structured block so a
            # non-LLM client (e.g. mcp-inspector) can preview it cleanly.
            _text(
                "assistant",
                "Tool input (JSON):\n"
                + _json_block(payload),
            ),
        ],
    }


def _build_state_of_mind(args: Dict[str, Any]) -> Dict[str, Any]:
    days = _coerce_int(args.get("days"), default=7, low=1, high=365)
    # Diary `last_n` is entries, not days — assume <=5 entries/day average,
    # cap at 100 (the tool's own ceiling). Filter by date client-side.
    last_n = min(days * 5, 100)
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    instruction = (
        f"The user invoked `/state-of-mind days={days}`. Build a "
        f"'last {days} days in numbers' summary.\n\n"
        f"1. Call `mempalace_diary_read`:\n"
        f'   {{"agent_name": "user", "last_n": {last_n}}}\n'
        f"   Filter the returned entries to those with `date` >= {cutoff!r}.\n\n"
        f"2. Call `mempalace_kg_timeline` with no entity filter:\n"
        f'   {{}}\n'
        f"   Filter the returned facts to those whose `valid_from` "
        f"(or `added_at` if no `valid_from`) is >= {cutoff!r}.\n\n"
        f"3. Compose the response with these sections:\n"
        f"   - **Mood arc** — count entries by `topic` prefix `mood:` "
        f"(low/normal/high). Show the trend, not just the totals.\n"
        f"   - **Themes** — group diary topics; surface the top 3.\n"
        f"   - **What changed** — list KG facts added in window, sorted "
        f"by date.\n"
        f"   - **Headline** — one sentence: how was the period overall?\n\n"
        f"Be concise. The user wants a snapshot, not a full readback."
    )

    return {
        "description": f"State of mind — last {days} days",
        "messages": [
            _text("user", f"/state-of-mind days={days}"),
            _text("assistant", instruction),
        ],
    }


def _build_who_knows(args: Dict[str, Any]) -> Dict[str, Any]:
    person = (args.get("person") or "").strip()
    if not person:
        return {"_error": _err("`person` is required for /who-knows")}

    instruction = (
        f"The user invoked `/who-knows {person}`. Build a composed bio.\n\n"
        f"1. Call `mempalace_kg_query`:\n"
        f'   {{"entity": {person!r}, "direction": "both"}}\n'
        f"   This returns all typed facts where {person} is subject or object.\n\n"
        f"2. From step 1's results, collect the `wing` of any related "
        f"entity. For each unique wing, call `mempalace_follow_tunnels`:\n"
        f'   {{"wing": <wing>, "room": "people"}}\n'
        f"   (use `room: \"diary\"` if `people` returns nothing)\n"
        f"   This surfaces cross-wing references.\n\n"
        f"3. Call `mempalace_search`:\n"
        f'   {{"query": {person!r}, "limit": 10}}\n'
        f"   This finds drawers that mention {person} by name.\n\n"
        f"4. Optionally call `mempalace_kg_timeline`:\n"
        f'   {{"entity": {person!r}}}\n'
        f"   for a chronological view of facts about them.\n\n"
        f"5. Compose the bio in this order:\n"
        f"   - **Identity** (relationship facts: child_of, works_with, etc.)\n"
        f"   - **Current state** (loves, does, lives_in — present tense facts)\n"
        f"   - **Timeline** (key events, oldest → newest)\n"
        f"   - **Mentions** (drawers where the person appears, with dates)\n\n"
        f"If the KG returns zero hits, say so plainly — do not fabricate."
    )

    return {
        "description": f"Bio: {person}",
        "messages": [
            _text("user", f"/who-knows {person}"),
            _text("assistant", instruction),
        ],
    }


def _build_time_machine(args: Dict[str, Any]) -> Dict[str, Any]:
    date = (args.get("date") or "").strip()
    if not date:
        return {"_error": _err("`date` is required for /time-machine")}
    if not _ISO_DATE_RE.match(date):
        return {"_error": _err("`date` must be ISO format YYYY-MM-DD")}

    instruction = (
        f"The user invoked `/time-machine {date}`. Reconstruct that day.\n\n"
        f"1. Call `mempalace_diary_read`:\n"
        f'   {{"agent_name": "user", "last_n": 100}}\n'
        f"   Filter to entries where `date` == {date!r}.\n\n"
        f"2. Call `mempalace_kg_timeline`:\n"
        f'   {{}}\n'
        f"   Filter to facts where `valid_from` == {date!r} OR "
        f"`ended` == {date!r} (facts that became true / ended that day).\n\n"
        f"3. Call `mempalace_list_drawers`:\n"
        f'   {{"limit": 100, "offset": 0}}\n'
        f"   Filter client-side to drawers whose `filed_at` starts with "
        f"{date!r} (drawers created that day).\n\n"
        f"4. Compose the day's reconstruction:\n"
        f"   - **Diary** — what the user wrote, in chronological order.\n"
        f"   - **What became true** — KG facts validated that day.\n"
        f"   - **What ended** — KG facts invalidated that day.\n"
        f"   - **New drawers** — IDs + first-line preview.\n\n"
        f"If no data exists for the date, say so explicitly."
    )

    return {
        "description": f"Time machine: {date}",
        "messages": [
            _text("user", f"/time-machine {date}"),
            _text("assistant", instruction),
        ],
    }


def _build_connect(args: Dict[str, Any]) -> Dict[str, Any]:
    topic1 = (args.get("topic1") or "").strip()
    topic2 = (args.get("topic2") or "").strip()
    if not topic1 or not topic2:
        return {"_error": _err("Both `topic1` and `topic2` are required")}

    instruction = (
        f"The user invoked `/connect {topic1} {topic2}`. Find the narrative "
        f"chain between these two entities in the knowledge graph.\n\n"
        f"PolyPalace has no native graph-path tool, so simulate BFS:\n\n"
        f"1. Call `mempalace_kg_query` for {topic1!r}:\n"
        f'   {{"entity": {topic1!r}, "direction": "both"}}\n'
        f"   Collect every neighbour entity. This is your frontier-1.\n\n"
        f"2. For each frontier-1 neighbour, call `mempalace_kg_query` "
        f"again. If any of their neighbours equals {topic2!r}, you have "
        f"a 2-hop path. Stop here.\n\n"
        f"3. If no 2-hop path is found after exhausting frontier-1, "
        f"expand one more hop (frontier-2). Cap total queries at 12 to "
        f"avoid runaway. If still nothing, fall back to:\n"
        f"   - `mempalace_search`: query = {topic1!r} + ' ' + {topic2!r}, "
        f"limit 5 — surfaces drawers mentioning both.\n\n"
        f"4. Output:\n"
        f"   - **Path** — A → predicate → B → predicate → C, with hop count.\n"
        f"   - **Narrative** — one paragraph: 'You connected {topic1} to "
        f"{topic2} through ...' (use the predicates as verbs).\n"
        f"   - **Sources** — drawer/closet IDs cited by KG facts on the path.\n\n"
        f"If no path exists at all, say so — do not invent a connection."
    )

    return {
        "description": f"Connect: {topic1} ↔ {topic2}",
        "messages": [
            _text("user", f"/connect {topic1} {topic2}"),
            _text("assistant", instruction),
        ],
    }


def _build_forget_old(args: Dict[str, Any]) -> Dict[str, Any]:
    days = _coerce_int(args.get("days"), default=90, low=7, high=3650)
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    instruction = (
        f"The user invoked `/forget-old days={days}`. Surface stale drawers "
        f"and ask for a prune decision per drawer.\n\n"
        f"1. Call `mempalace_list_drawers`:\n"
        f'   {{"limit": 100, "offset": 0}}\n'
        f"   Paginate (offset += 100) until the result count is < 100.\n\n"
        f"2. For each drawer, read `last_accessed` if present, otherwise "
        f"fall back to `filed_at`. Keep only drawers where that timestamp "
        f"is older than {cutoff!r}.\n\n"
        f"3. Group the stale drawers by `wing`. Within each group, sort "
        f"oldest-first.\n\n"
        f"4. Render the response as a checklist. For each drawer show:\n"
        f"   - drawer_id\n"
        f"   - wing/room\n"
        f"   - first 80 chars of content\n"
        f"   - last activity date\n"
        f"   - suggested action: **archive** if it looks like reference "
        f"material; **delete** if obviously trivial; **keep** if it "
        f"references an entity that still appears in recent diary or KG.\n\n"
        f"5. End with a single prompt to the user: 'Reply with the IDs to "
        f"delete, or `none` to skip.' Do not delete anything yourself — "
        f"the user must confirm IDs explicitly before any "
        f"`mempalace_delete_drawer` call.\n\n"
        f"If the MCP client supports elicitation, you may use it instead "
        f"of the textual confirmation prompt."
    )

    return {
        "description": f"Stale drawers (older than {days} days)",
        "messages": [
            _text("user", f"/forget-old days={days}"),
            _text("assistant", instruction),
        ],
    }


def _build_whats_on_my_mind(args: Dict[str, Any]) -> Dict[str, Any]:
    hours = _coerce_int(args.get("hours"), default=24, low=1, high=720)
    cutoff_dt = datetime.now() - timedelta(hours=hours)
    cutoff_iso = cutoff_dt.isoformat(timespec="seconds")

    instruction = (
        f"The user invoked `/whats-on-my-mind hours={hours}`. Snapshot what "
        f"the user has been thinking about in the last {hours} hours.\n\n"
        f"1. Call `mempalace_kg_timeline`:\n"
        f'   {{}}\n'
        f"   Filter facts to those whose `added_at` (or `valid_from` "
        f"fallback) is >= {cutoff_iso!r}.\n\n"
        f"2. Call `mempalace_diary_read`:\n"
        f'   {{"agent_name": "user", "last_n": 30}}\n'
        f"   Filter to entries with `timestamp` >= {cutoff_iso!r}.\n\n"
        f"3. Group the combined items by their main entity / topic. "
        f"Surface the top 3 clusters by frequency.\n\n"
        f"4. Render:\n"
        f"   - **Top theme** — one sentence + a count.\n"
        f"   - **Also on your mind** — bullet list of secondary themes.\n"
        f"   - **New entities** — anything that appears in the KG for the "
        f"first time in this window.\n\n"
        f"Keep the whole response under 200 words. This is a passive "
        f"snapshot, not an essay."
    )

    return {
        "description": f"What's on my mind — last {hours}h",
        "messages": [
            _text("user", f"/whats-on-my-mind hours={hours}"),
            _text("assistant", instruction),
        ],
    }


_PROMPT_HANDLERS = {
    "recall": _build_recall,
    "journal": _build_journal,
    "state-of-mind": _build_state_of_mind,
    "who-knows": _build_who_knows,
    "time-machine": _build_time_machine,
    "connect": _build_connect,
    "forget-old": _build_forget_old,
    "whats-on-my-mind": _build_whats_on_my_mind,
}


# ---------------------------------------------------------------------------
# 6. Public handler: completion/complete
# ---------------------------------------------------------------------------
#
# MCP `completion/complete` lets the client autocomplete a prompt argument
# while the user is still typing. It receives:
#
#   {
#     "ref":      { "type": "ref/prompt", "name": "<prompt-name>" },
#     "argument": { "name": "<arg-name>", "value": "<partial-text>" },
#     "context":  { "arguments": { ... already-filled args ... } }   # optional
#   }
#
# and must return:
#
#   {
#     "completion": {
#       "values": [str, ...],   # up to 100 suggestions
#       "total":  int,           # optional — total available
#       "hasMore": bool          # optional — true if values is truncated
#     }
#   }
#
# Suggestions here are derived from live palace state via callbacks the
# server passes in. We expose `complete_prompt_argument(ref, argument,
# context, *, palace_lookup=None)` so wiring stays explicit.


def complete_prompt_argument(
    ref: Dict[str, Any],
    argument: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
    *,
    palace_lookup: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build the response payload for `completion/complete`.

    `palace_lookup` is an optional dict of callables the server passes in:
        {
          "kg_entities":    () -> List[str],   # all entities in the KG
          "diary_topics":   () -> List[str],   # distinct diary topics
          "drawer_ids":     () -> List[str],
          "diary_dates":    () -> List[str],   # YYYY-MM-DD strings
        }
    Any missing callable just disables suggestions for that field —
    completion is always best-effort.
    """
    palace_lookup = palace_lookup or {}

    if (ref or {}).get("type") != "ref/prompt":
        return {"completion": {"values": [], "total": 0, "hasMore": False}}

    prompt_name = (ref or {}).get("name") or ""
    arg_name = (argument or {}).get("name") or ""
    partial = ((argument or {}).get("value") or "").lower().strip()

    # Map (prompt, argument) → suggestion source.
    suggestions: List[str] = []

    if prompt_name == "recall" and arg_name == "topic":
        suggestions = _suggest(palace_lookup.get("kg_entities"), palace_lookup.get("diary_topics"))
    elif prompt_name == "who-knows" and arg_name == "person":
        suggestions = _suggest(palace_lookup.get("kg_entities"))
    elif prompt_name == "time-machine" and arg_name == "date":
        suggestions = _suggest(palace_lookup.get("diary_dates"))
    elif prompt_name == "connect" and arg_name in {"topic1", "topic2"}:
        suggestions = _suggest(palace_lookup.get("kg_entities"))
    elif prompt_name == "journal" and arg_name == "mood":
        suggestions = ["low", "normal", "high"]
    elif prompt_name == "journal" and arg_name == "tags":
        # No completion for free-form comma-list; clients can suggest from
        # past topics if desired.
        suggestions = _suggest(palace_lookup.get("diary_topics"))
    elif prompt_name == "state-of-mind" and arg_name == "days":
        suggestions = ["7", "14", "30", "90"]
    elif prompt_name == "forget-old" and arg_name == "days":
        suggestions = ["30", "60", "90", "180", "365"]
    elif prompt_name == "whats-on-my-mind" and arg_name == "hours":
        suggestions = ["6", "12", "24", "48", "72"]

    # Prefix-filter, dedupe, keep order.
    seen = set()
    filtered: List[str] = []
    for s in suggestions:
        if not isinstance(s, str):
            continue
        if partial and not s.lower().startswith(partial):
            continue
        if s in seen:
            continue
        seen.add(s)
        filtered.append(s)
        if len(filtered) >= 100:
            break

    return {
        "completion": {
            "values": filtered,
            "total": len(filtered),
            "hasMore": False,
        }
    }


def _suggest(*sources) -> List[str]:
    """Concatenate suggestion sources, calling each callable lazily."""
    out: List[str] = []
    for src in sources:
        if src is None:
            continue
        try:
            values = src() if callable(src) else src
        except Exception:
            continue
        if isinstance(values, list):
            out.extend(v for v in values if isinstance(v, str))
    return out


# ---------------------------------------------------------------------------
# 7. Internal helpers
# ---------------------------------------------------------------------------


def _json_block(payload: Dict[str, Any]) -> str:
    """Pretty-print a small dict for embedding inside an instruction message.

    We avoid `json.dumps(indent=2)` to keep the module zero-dep at import
    time (it's already imported at server top-level) — but we *do* use it
    here because the server already imports json. Inline import keeps this
    file self-contained for unit testing without the rest of mcp_server.
    """
    import json as _json

    return _json.dumps(payload, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 8. Quick self-check (runs only when this file is executed directly)
# ---------------------------------------------------------------------------


if __name__ == "__main__":  # pragma: no cover
    import json

    print("=== prompts/list ===")
    print(json.dumps(list_prompts(), indent=2, ensure_ascii=False))

    print("\n=== prompts/get recall topic=fiverr ===")
    print(json.dumps(get_prompt("recall", {"topic": "fiverr"}), indent=2, ensure_ascii=False))

    print("\n=== prompts/get journal entry='Shipped Gig 1!' mood=high tags=fiverr,launch ===")
    print(
        json.dumps(
            get_prompt(
                "journal",
                {"entry": "Shipped Gig 1!", "mood": "high", "tags": "fiverr,launch"},
            ),
            indent=2,
            ensure_ascii=False,
        )
    )

    print("\n=== completion/complete who-knows partial='Ma' ===")
    fake_lookup = {"kg_entities": lambda: ["Max", "Maria", "Alice", "Bob"]}
    print(
        json.dumps(
            complete_prompt_argument(
                {"type": "ref/prompt", "name": "who-knows"},
                {"name": "person", "value": "Ma"},
                palace_lookup=fake_lookup,
            ),
            indent=2,
            ensure_ascii=False,
        )
    )
