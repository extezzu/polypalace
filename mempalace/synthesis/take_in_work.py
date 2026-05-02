"""
take_in_work — MCP tool: mark a TG Saved Message as "taken into work" (deletes it).

Semantic: when user takes a task/idea from Saved Messages into active work,
the message is removed from the synthesis pipeline. After this, future
`whats_new` calls won't show it — focus stays on un-started items only.

Usage flow:
  1. User asks Claude "Шо слышно?" → whats_new lists TG saved items with composite IDs.
  2. User says "I'll take that AI brain idea into work" / "беру в работу X".
  3. Claude finds matching item from recent output, calls this tool with
     confirm=True after intent is clear.
  4. Tool deletes from TG Saved Messages permanently (revoke=True).

Safety:
  - Tool requires explicit confirm=True parameter — refuses to delete otherwise.
  - Claude should ALWAYS verify message identity with user before calling
    (e.g., quote first 60 chars and ask "this one?").
"""

from __future__ import annotations

from .sources import tg_live


def take_in_work(message_id: str, confirm: bool = False) -> dict:
    """
    Mark a TG Saved Message as taken into work (deletes from Saved Messages).

    Args:
        message_id: composite ID from whats_new/surface_ideas output (e.g. "196993:42").
        confirm: must be True. Safety gate.

    Returns:
        dict with operation status.
    """
    return tg_live.take_in_work(message_id=message_id, confirm=confirm)
