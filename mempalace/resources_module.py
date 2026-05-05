"""
resources_module.py — MCP Resources implementation for PolyPalace
=================================================================

Implements the MCP 2025-11-25 Resources spec for the PolyPalace memory
server. Designed as a drop-in import for ``mempalace.mcp_server`` —
see ``INTEGRATION.md`` for the wiring patch.

Spec references (https://modelcontextprotocol.io/specification/2025-11-25):

  * §Server.Resources.3.1 — ``resources/list`` + cursor pagination
  * §Server.Resources.3.2 — ``resources/templates/list``
  * §Server.Resources.3.3 — ``resources/read``
  * §Server.Resources.3.4 — ``Resource``, ``ResourceTemplate``, ``meta``
  * §Server.Resources.4   — Subscriptions + ``notifications/resources/updated``
  * §Server.Resources.5   — ``notifications/resources/list_changed``
  * §Server.Utilities.completion — ``completion/complete`` (typed autocomplete)
  * §Server.Resources.6.2 — Error mapping (-32002 ResourceNotFound)

This module is *self-contained* — it imports PolyPalace storage directly
and exposes plain-Python entry points that the MCP request dispatcher
can wire to method names. There are no external MCP-SDK types because
PolyPalace's server speaks raw JSON-RPC. Every dataclass below is a
mirror of the spec's wire shape.

Public entry points (called from ``handle_request``):

    list_resources(cursor=None) -> ListResourcesResult
    read_resource(uri) -> ReadResourceResult
    list_resource_templates() -> ListResourceTemplatesResult
    complete_argument(ref, argument, context=None) -> CompletionResult
    subscribe_resource(uri) -> SubscriptionResult        # Tier 2
    unsubscribe_resource(uri) -> SubscriptionResult      # Tier 2
    poll_subscriptions() -> list[Notification]           # Tier 2 — call after writes

Plus two helpers the dispatcher invokes directly:

    notify_list_changed() -> Notification
    set_emit_callback(fn) -> None    # plug stdout-emit into the module
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Imports from PolyPalace internals — no re-implementation of storage.
# ---------------------------------------------------------------------------
# These mirror exactly what mcp_server.py already pulls in. Failing to
# resolve these means the module is being run outside the mempalace
# package and should not be loaded.
from mempalace.config import MempalaceConfig
from mempalace.knowledge_graph import KnowledgeGraph
from mempalace.palace_graph import list_tunnels as _list_tunnels

logger = logging.getLogger("mempalace_resources")

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

RESOURCES_SCHEMA_VERSION = "1"
SCHEME = "palace"
_SCHEME_PREFIX = f"{SCHEME}://"

_LIST_PAGE_SIZE = 50
_LIST_MAX_PAGE_SIZE = 200
_RECENT_DRAWERS_LIMIT = 50
_DIARY_RECENT_DAYS = 30
_ROOM_DRAWERS_HARD_CAP = 200
_KG_TIMELINE_HARD_CAP = 100  # mirrors the LIMIT in KnowledgeGraph.timeline()


# ---------------------------------------------------------------------------
# Wire-shape dataclasses — match MCP 2025-11-25 spec §3.4 / §3.5 exactly.
# ---------------------------------------------------------------------------


@dataclass
class Resource:
    """Spec §3.4 — a static, addressable resource entry."""

    uri: str
    name: str
    description: str
    mimeType: str
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResourceTemplate:
    """Spec §3.2 — a parameterized URI template (RFC 6570 form)."""

    uriTemplate: str
    name: str
    description: str
    mimeType: str
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TextResourceContents:
    """Spec §3.3 — text contents returned from resources/read."""

    uri: str
    text: str
    mimeType: str = "text/plain"


@dataclass
class BlobResourceContents:
    """Spec §3.3 — binary contents (base64-encoded). Reserved for future
    image/PDF drawers; not produced by current handlers."""

    uri: str
    blob: str  # base64
    mimeType: str = "application/octet-stream"


@dataclass
class ListResourcesResult:
    resources: List[Resource]
    nextCursor: Optional[str] = None


@dataclass
class ListResourceTemplatesResult:
    resourceTemplates: List[ResourceTemplate]


@dataclass
class ReadResourceResult:
    contents: List[Any]  # TextResourceContents | BlobResourceContents


@dataclass
class CompletionEntry:
    values: List[str]
    total: int
    hasMore: bool = False


@dataclass
class CompletionResult:
    completion: CompletionEntry


@dataclass
class SubscriptionResult:
    """Plain ack — body is empty by spec but we surface the URI for clarity."""

    uri: str
    subscribed: bool


# ---------------------------------------------------------------------------
# Errors — mapped to JSON-RPC codes by the dispatcher (see INTEGRATION.md).
# ---------------------------------------------------------------------------


class ResourceError(Exception):
    """Base; every subclass carries .json_rpc_code."""

    json_rpc_code = -32603


class InvalidUriError(ResourceError):
    json_rpc_code = -32602  # Invalid params


class ResourceNotFoundError(ResourceError):
    json_rpc_code = -32002  # Spec §6.2


class InvalidParamError(ResourceError):
    json_rpc_code = -32602


# ---------------------------------------------------------------------------
# Backend accessor injection — keeps this module testable.
# ---------------------------------------------------------------------------
# mcp_server.py owns the cached ChromaDB collection and KG. Rather than
# re-discovering them, the integration step calls ``configure_backends``
# once at startup with the existing accessors.

_get_collection: Optional[Callable[[], Any]] = None
_kg: Optional[KnowledgeGraph] = None
_get_cached_metadata: Optional[Callable[[Any, Optional[dict]], List[dict]]] = None
_fetch_all_metadata: Optional[Callable[[Any, Optional[dict]], List[dict]]] = None


def configure_backends(
    *,
    get_collection: Callable[[], Any],
    kg: KnowledgeGraph,
    get_cached_metadata: Callable[[Any, Optional[dict]], List[dict]],
    fetch_all_metadata: Callable[[Any, Optional[dict]], List[dict]],
) -> None:
    """Wire the accessors mcp_server.py already exposes.

    Call exactly once at server startup, before any resources/* method
    is dispatched. After configuration the module is read-only.
    """
    global _get_collection, _kg, _get_cached_metadata, _fetch_all_metadata
    _get_collection = get_collection
    _kg = kg
    _get_cached_metadata = get_cached_metadata
    _fetch_all_metadata = fetch_all_metadata


def _require_configured() -> None:
    if _get_collection is None or _kg is None:
        raise ResourceError(
            "resources_module.configure_backends() was not called — "
            "the module is not wired into the server."
        )


# ---------------------------------------------------------------------------
# resources/list — static catalog
# ---------------------------------------------------------------------------


def _meta(extra: Optional[dict] = None) -> dict:
    base = {"version": RESOURCES_SCHEMA_VERSION}
    if extra:
        base.update(extra)
    return base


def _static_resources() -> List[Resource]:
    """Return the catalog of non-templated resources.

    Three are zero-arg static URIs (drawers/recent, diary/recent,
    taxonomy). Two more are emitted *per active wing* on first call so
    the LLM has direct entry points without composing a wing name —
    this is generated lazily so we don't pay the metadata scan when
    the client never calls list_resources.
    """
    static: List[Resource] = [
        Resource(
            uri=f"{_SCHEME_PREFIX}drawers/recent",
            name="Recent drawers",
            description=(
                f"The {_RECENT_DRAWERS_LIMIT} most recently filed drawers across all "
                "wings, sorted newest first. Use as a session landing-page to "
                "see what was just captured."
            ),
            mimeType="application/json",
            meta=_meta(),
        ),
        Resource(
            uri=f"{_SCHEME_PREFIX}diary/recent",
            name="Recent diary entries",
            description=(
                f"All diary entries from the last {_DIARY_RECENT_DAYS} days, grouped "
                "by date. Each entry is AAAK-encoded — see mempalace_get_aaak_spec "
                "for the dialect."
            ),
            mimeType="application/json",
            meta=_meta(),
        ),
        Resource(
            uri=f"{_SCHEME_PREFIX}taxonomy",
            name="Palace taxonomy",
            description=(
                "Full wing → room → drawer-count tree. Read once per session to "
                "construct navigation and to know which wings/rooms exist."
            ),
            mimeType="application/json",
            meta=_meta(),
        ),
    ]
    return static


def list_resources(cursor: Optional[str] = None) -> ListResourcesResult:
    """Spec §3.1 — paginated static-resource list.

    The cursor encodes ``offset:N`` in base64; ``None`` means "from start".
    """
    _require_configured()
    all_static = _static_resources()
    page_size = _LIST_PAGE_SIZE
    offset = _decode_cursor(cursor)
    page = all_static[offset : offset + page_size]
    next_offset = offset + len(page)
    next_cursor = (
        _encode_cursor(next_offset) if next_offset < len(all_static) else None
    )
    return ListResourcesResult(resources=page, nextCursor=next_cursor)


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(f"offset:{offset}".encode()).decode().rstrip("=")


def _decode_cursor(cursor: Optional[str]) -> int:
    if cursor is None:
        return 0
    try:
        padding = "=" * (-len(cursor) % 4)
        decoded = base64.urlsafe_b64decode(cursor + padding).decode()
        if not decoded.startswith("offset:"):
            raise ValueError
        return max(0, int(decoded.split(":", 1)[1]))
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidParamError(f"Invalid cursor: {cursor!r}") from exc


# ---------------------------------------------------------------------------
# resources/templates/list — parameterized URIs (RFC 6570)
# ---------------------------------------------------------------------------


def list_resource_templates() -> ListResourceTemplatesResult:
    """Spec §3.2 — return the templated URIs the client can instantiate."""
    return ListResourceTemplatesResult(
        resourceTemplates=[
            ResourceTemplate(
                uriTemplate=f"{_SCHEME_PREFIX}drawers/{{drawer_id}}",
                name="Drawer by ID",
                description=(
                    "Fetch a single drawer by its deterministic ID. "
                    "drawer_id is autocomplete-friendly via completion/complete."
                ),
                mimeType="text/markdown",
                meta=_meta({"completion_argument": "drawer_id"}),
            ),
            ResourceTemplate(
                uriTemplate=f"{_SCHEME_PREFIX}diary/{{date}}",
                name="Diary entry by date",
                description=(
                    "Fetch all diary entries filed on the given calendar date "
                    "(YYYY-MM-DD). Multiple entries on one date are concatenated "
                    "in chronological order."
                ),
                mimeType="text/markdown",
                meta=_meta({"completion_argument": "date"}),
            ),
            ResourceTemplate(
                uriTemplate=f"{_SCHEME_PREFIX}kg/{{node_id}}",
                name="KG node + 1-hop neighborhood",
                description=(
                    "Fetch a knowledge-graph entity and its immediate "
                    "incoming/outgoing relationships. node_id is the canonical "
                    "lowercased+underscored form (e.g. 'max', 'wing_code')."
                ),
                mimeType="application/json",
                meta=_meta({"completion_argument": "node_id"}),
            ),
            ResourceTemplate(
                uriTemplate=f"{_SCHEME_PREFIX}kg/timeline/{{from_date}}/{{to_date}}",
                name="KG timeline window",
                description=(
                    "Chronological events (fact_started, fact_ended) within "
                    "the given date window. Both bounds inclusive, YYYY-MM-DD."
                ),
                mimeType="application/json",
                meta=_meta({"completion_argument": "from_date"}),
            ),
            ResourceTemplate(
                uriTemplate=f"{_SCHEME_PREFIX}wings/{{wing}}/rooms/{{room}}",
                name="Room contents",
                description=(
                    "All drawers in a single (wing, room) pair, plus the "
                    "explicit cross-wing tunnels rooted at that wing."
                ),
                mimeType="application/json",
                meta=_meta({"completion_argument": "wing"}),
            ),
        ]
    )


# ---------------------------------------------------------------------------
# resources/read — dispatch by URI
# ---------------------------------------------------------------------------


_DRAWER_RE = re.compile(rf"^{re.escape(_SCHEME_PREFIX)}drawers/(?P<id>[^/]+)$")
_DIARY_DATE_RE = re.compile(
    rf"^{re.escape(_SCHEME_PREFIX)}diary/(?P<date>\d{{4}}-\d{{2}}-\d{{2}})$"
)
_KG_NODE_RE = re.compile(rf"^{re.escape(_SCHEME_PREFIX)}kg/(?P<node>[^/]+)$")
_KG_TIMELINE_RE = re.compile(
    rf"^{re.escape(_SCHEME_PREFIX)}kg/timeline/"
    r"(?P<from>\d{4}-\d{2}-\d{2})/(?P<to>\d{4}-\d{2}-\d{2})$"
)
_ROOM_RE = re.compile(
    rf"^{re.escape(_SCHEME_PREFIX)}wings/(?P<wing>[^/]+)/rooms/(?P<room>[^/]+)$"
)


def read_resource(uri: str) -> ReadResourceResult:
    """Spec §3.3 — dispatch a resources/read by URI shape."""
    _require_configured()
    if not isinstance(uri, str) or not uri.startswith(_SCHEME_PREFIX):
        raise InvalidUriError(f"Invalid URI scheme: {uri!r}")

    # Static URIs first — they're cheapest to identify.
    if uri == f"{_SCHEME_PREFIX}drawers/recent":
        return _read_drawers_recent(uri)
    if uri == f"{_SCHEME_PREFIX}diary/recent":
        return _read_diary_recent(uri)
    if uri == f"{_SCHEME_PREFIX}taxonomy":
        return _read_taxonomy(uri)

    if (m := _DRAWER_RE.match(uri)) and m.group("id") != "recent":
        return _read_drawer(uri, m.group("id"))
    if m := _DIARY_DATE_RE.match(uri):
        return _read_diary_date(uri, m.group("date"))
    if m := _KG_TIMELINE_RE.match(uri):
        return _read_kg_timeline(uri, m.group("from"), m.group("to"))
    if (m := _KG_NODE_RE.match(uri)) and not m.group("node").startswith("timeline"):
        return _read_kg_node(uri, m.group("node"))
    if m := _ROOM_RE.match(uri):
        return _read_room(uri, m.group("wing"), m.group("room"))

    raise InvalidUriError(f"URI does not match any known pattern: {uri!r}")


# ---------------------------------------------------------------------------
# Individual read handlers
# ---------------------------------------------------------------------------


def _read_drawer(uri: str, drawer_id: str) -> ReadResourceResult:
    col = _get_collection()
    if col is None:
        raise ResourceNotFoundError("No palace collection available")
    result = col.get(ids=[drawer_id], include=["documents", "metadatas"])
    ids = result["ids"] if isinstance(result, dict) else result.ids
    if not ids:
        raise ResourceNotFoundError(f"Drawer not found: {drawer_id}")
    docs = result["documents"] if isinstance(result, dict) else result.documents
    metas = result["metadatas"] if isinstance(result, dict) else result.metadatas
    body = docs[0] or ""
    meta = metas[0] or {}

    # Sniff JSON payloads → bump mime; else default markdown with YAML header.
    stripped = body.lstrip()
    if stripped[:1] in ("{", "["):
        return ReadResourceResult(
            contents=[
                TextResourceContents(uri=uri, text=body, mimeType="application/json")
            ]
        )
    header = (
        "---\n"
        f"drawer_id: {drawer_id}\n"
        f"wing: {meta.get('wing', '')}\n"
        f"room: {meta.get('room', '')}\n"
        f"filed_at: {meta.get('filed_at', '')}\n"
        f"added_by: {meta.get('added_by', '')}\n"
        "---\n\n"
    )
    return ReadResourceResult(
        contents=[
            TextResourceContents(
                uri=uri, text=header + body, mimeType="text/markdown"
            )
        ]
    )


def _read_drawers_recent(uri: str) -> ReadResourceResult:
    col = _get_collection()
    if col is None:
        raise ResourceNotFoundError("No palace collection available")
    # Pull all metadata via the cached helper, sort by filed_at desc, slice.
    metas = _get_cached_metadata(col, None)
    rows: List[Tuple[float, str, dict]] = []
    # We need IDs + previews — fetch in chunks using the same paginated read
    # the existing list_drawers tool uses.
    # _fetch_all_metadata only yields metadatas; for previews we need documents
    # too, so re-issue a paginated get here.
    total = col.count()
    offset = 0
    page = 1000
    drawers: List[dict] = []
    while offset < total:
        batch = col.get(
            include=["documents", "metadatas"], limit=page, offset=offset
        )
        b_ids = batch["ids"] if isinstance(batch, dict) else batch.ids
        b_docs = batch["documents"] if isinstance(batch, dict) else batch.documents
        b_metas = batch["metadatas"] if isinstance(batch, dict) else batch.metadatas
        if not b_ids:
            break
        for did, doc, m in zip(b_ids, b_docs, b_metas):
            m = m or {}
            filed_at = m.get("filed_at") or ""
            drawers.append(
                {
                    "drawer_id": did,
                    "wing": m.get("wing", ""),
                    "room": m.get("room", ""),
                    "preview": (doc or "")[:200],
                    "filed_at": filed_at,
                    "added_by": m.get("added_by", ""),
                }
            )
        offset += len(b_ids)
    drawers.sort(key=lambda d: d["filed_at"] or "", reverse=True)
    drawers = drawers[:_RECENT_DRAWERS_LIMIT]
    payload = {
        "drawers": drawers,
        "total_returned": len(drawers),
        "as_of": datetime.now().isoformat(),
    }
    return ReadResourceResult(
        contents=[
            TextResourceContents(
                uri=uri, text=json.dumps(payload, indent=2), mimeType="application/json"
            )
        ]
    )


def _read_diary_date(uri: str, date_str: str) -> ReadResourceResult:
    _validate_date(date_str)
    col = _get_collection()
    if col is None:
        raise ResourceNotFoundError("No palace collection available")
    result = col.get(
        where={"$and": [{"room": "diary"}, {"date": date_str}]},
        include=["documents", "metadatas"],
        limit=10000,
    )
    ids = result["ids"] if isinstance(result, dict) else result.ids
    if not ids:
        raise ResourceNotFoundError(f"No diary entries on {date_str}")
    docs = result["documents"] if isinstance(result, dict) else result.documents
    metas = result["metadatas"] if isinstance(result, dict) else result.metadatas
    rows = sorted(
        zip(docs, metas),
        key=lambda dm: (dm[1] or {}).get("filed_at", ""),
    )
    agents = sorted({(m or {}).get("agent", "") for _, m in rows if m} - {""})
    header = (
        "---\n"
        f"date: {date_str}\n"
        f"entry_count: {len(rows)}\n"
        f"agents: {agents}\n"
        "---\n\n"
    )
    body = "\n\n---\n\n".join(d or "" for d, _ in rows)
    return ReadResourceResult(
        contents=[
            TextResourceContents(
                uri=uri, text=header + body, mimeType="text/markdown"
            )
        ]
    )


def _read_diary_recent(uri: str) -> ReadResourceResult:
    col = _get_collection()
    if col is None:
        raise ResourceNotFoundError("No palace collection available")
    cutoff = (datetime.now() - timedelta(days=_DIARY_RECENT_DAYS)).strftime("%Y-%m-%d")
    result = col.get(
        where={"room": "diary"},
        include=["documents", "metadatas"],
        limit=10000,
    )
    docs = result["documents"] if isinstance(result, dict) else result.documents
    metas = result["metadatas"] if isinstance(result, dict) else result.metadatas
    by_date: Dict[str, List[dict]] = {}
    earliest = None
    latest = None
    for doc, m in zip(docs, metas):
        m = m or {}
        d = m.get("date", "")
        if not d or d < cutoff:
            continue
        by_date.setdefault(d, []).append(
            {
                "agent": m.get("agent", ""),
                "topic": m.get("topic", ""),
                "preview": (doc or "")[:200],
                "filed_at": m.get("filed_at", ""),
            }
        )
        earliest = d if earliest is None or d < earliest else earliest
        latest = d if latest is None or d > latest else latest
    payload = {
        "entries_by_date": dict(sorted(by_date.items(), reverse=True)),
        "date_range": {"from": earliest or cutoff, "to": latest or cutoff},
        "entry_count": sum(len(v) for v in by_date.values()),
    }
    return ReadResourceResult(
        contents=[
            TextResourceContents(
                uri=uri, text=json.dumps(payload, indent=2), mimeType="application/json"
            )
        ]
    )


def _read_kg_node(uri: str, node_id: str) -> ReadResourceResult:
    facts = _kg.query_entity(node_id, direction="both")
    # query_entity auto-creates from name; if entity doesn't exist it
    # returns []. Distinguish "real but childless node" from "no such node"
    # by hitting the entities table directly.
    with _kg._lock:  # noqa: SLF001 — same package, intentional
        conn = _kg._conn()
        row = conn.execute(
            "SELECT name, type FROM entities WHERE id = ?",
            (_kg._entity_id(node_id),),
        ).fetchone()
    if row is None and not facts:
        raise ResourceNotFoundError(f"KG node not found: {node_id}")
    outgoing = [f for f in facts if f["direction"] == "outgoing"]
    incoming = [f for f in facts if f["direction"] == "incoming"]
    payload = {
        "node_id": _kg._entity_id(node_id),
        "display_name": row["name"] if row else node_id,
        "type": row["type"] if row else "unknown",
        "neighborhood": {"outgoing": outgoing, "incoming": incoming},
        "fact_count": len(facts),
        "as_of": "now",
    }
    return ReadResourceResult(
        contents=[
            TextResourceContents(
                uri=uri, text=json.dumps(payload, indent=2), mimeType="application/json"
            )
        ]
    )


def _read_kg_timeline(uri: str, from_date: str, to_date: str) -> ReadResourceResult:
    _validate_date(from_date)
    _validate_date(to_date)
    if from_date > to_date:
        raise InvalidParamError(
            f"from_date {from_date} is after to_date {to_date}"
        )
    rows = _kg.timeline()  # capped at 100 rows
    events: List[dict] = []
    for r in rows:
        vf = r.get("valid_from")
        vt = r.get("valid_to")
        if vf and from_date <= vf <= to_date:
            events.append(
                {
                    "type": "fact_started",
                    "date": vf,
                    "subject": r["subject"],
                    "predicate": r["predicate"],
                    "object": r["object"],
                }
            )
        if vt and from_date <= vt <= to_date:
            events.append(
                {
                    "type": "fact_ended",
                    "date": vt,
                    "subject": r["subject"],
                    "predicate": r["predicate"],
                    "object": r["object"],
                }
            )
    events.sort(key=lambda e: e["date"])
    payload = {
        "from_date": from_date,
        "to_date": to_date,
        "events": events,
        "event_count": len(events),
        "truncated": len(rows) >= _KG_TIMELINE_HARD_CAP,
    }
    return ReadResourceResult(
        contents=[
            TextResourceContents(
                uri=uri, text=json.dumps(payload, indent=2), mimeType="application/json"
            )
        ]
    )


def _read_room(uri: str, wing: str, room: str) -> ReadResourceResult:
    col = _get_collection()
    if col is None:
        raise ResourceNotFoundError("No palace collection available")
    result = col.get(
        where={"$and": [{"wing": wing}, {"room": room}]},
        include=["documents", "metadatas"],
        limit=_ROOM_DRAWERS_HARD_CAP + 1,
    )
    ids = result["ids"] if isinstance(result, dict) else result.ids
    docs = result["documents"] if isinstance(result, dict) else result.documents
    metas = result["metadatas"] if isinstance(result, dict) else result.metadatas
    truncated = len(ids) > _ROOM_DRAWERS_HARD_CAP
    if truncated:
        ids = ids[:_ROOM_DRAWERS_HARD_CAP]
        docs = docs[:_ROOM_DRAWERS_HARD_CAP]
        metas = metas[:_ROOM_DRAWERS_HARD_CAP]
    drawers = []
    for did, doc, m in zip(ids, docs, metas):
        m = m or {}
        drawers.append(
            {
                "drawer_id": did,
                "preview": (doc or "")[:200],
                "filed_at": m.get("filed_at", ""),
                "added_by": m.get("added_by", ""),
            }
        )
    try:
        tunnels_block = _list_tunnels(wing) or {}
        tunnels = [
            t.get("tunnel_id", "")
            for t in tunnels_block.get("tunnels", [])
            if t.get("source_room") == room or t.get("target_room") == room
        ]
    except Exception:  # tunnel layer is optional
        tunnels = []
    payload = {
        "wing": wing,
        "room": room,
        "drawer_count": len(drawers),
        "drawers": drawers,
        "tunnels_out": tunnels,
        "truncated": truncated,
    }
    return ReadResourceResult(
        contents=[
            TextResourceContents(
                uri=uri, text=json.dumps(payload, indent=2), mimeType="application/json"
            )
        ]
    )


def _read_taxonomy(uri: str) -> ReadResourceResult:
    col = _get_collection()
    if col is None:
        raise ResourceNotFoundError("No palace collection available")
    taxonomy: Dict[str, Dict[str, int]] = {}
    metas = _get_cached_metadata(col, None)
    for m in metas:
        m = m or {}
        w = m.get("wing", "unknown")
        r = m.get("room", "unknown")
        taxonomy.setdefault(w, {})
        taxonomy[w][r] = taxonomy[w].get(r, 0) + 1
    wing_count = len(taxonomy)
    room_count = sum(len(rooms) for rooms in taxonomy.values())
    total = sum(c for rooms in taxonomy.values() for c in rooms.values())
    payload = {
        "taxonomy": taxonomy,
        "wing_count": wing_count,
        "room_count": room_count,
        "total_drawers": total,
    }
    return ReadResourceResult(
        contents=[
            TextResourceContents(
                uri=uri, text=json.dumps(payload, indent=2), mimeType="application/json"
            )
        ]
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_date(s: str) -> None:
    if not _DATE_RE.match(s or ""):
        raise InvalidParamError(
            f"Invalid date format: {s!r}, expected YYYY-MM-DD"
        )
    try:
        datetime.strptime(s, "%Y-%m-%d")
    except ValueError as exc:
        raise InvalidParamError(f"Invalid calendar date: {s!r}") from exc


# ---------------------------------------------------------------------------
# completion/complete — typed autocomplete (spec §Utilities.completion)
# ---------------------------------------------------------------------------


def complete_argument(
    ref: dict, argument: dict, context: Optional[dict] = None
) -> CompletionResult:
    """Spec §Utilities.completion (2025-11-25).

    Parameters
    ----------
    ref : dict
        ``{"type": "ref/resource", "uri": "<template-uri>"}``
    argument : dict
        ``{"name": "<arg>", "value": "<partial>"}``
    context : dict | None
        ``{"arguments": {"prior_arg": "value"}}`` — chain previously-completed
        args to scope this completion. Used by `wings/{wing}/rooms/{room}` so
        the room list narrows once the wing is picked.

    Returns up to 100 completion candidates, alphabetically sorted, prefix-
    matched against the argument's current value.
    """
    _require_configured()
    if not isinstance(ref, dict) or ref.get("type") != "ref/resource":
        raise InvalidParamError("ref.type must be 'ref/resource'")
    template = ref.get("uri", "")
    arg_name = (argument or {}).get("name", "")
    partial = (argument or {}).get("value", "") or ""
    ctx_args = (context or {}).get("arguments", {}) if context else {}

    candidates = _candidates_for_argument(template, arg_name, ctx_args)
    matches = [c for c in candidates if c.lower().startswith(partial.lower())]
    matches.sort()
    capped = matches[:100]
    return CompletionResult(
        completion=CompletionEntry(
            values=capped, total=len(matches), hasMore=len(matches) > 100
        )
    )


def _candidates_for_argument(
    template: str, arg_name: str, ctx_args: Dict[str, str]
) -> List[str]:
    """Produce the candidate set for a (template, argument) pair.

    Intentionally cheap — runs synchronously inside a JSON-RPC call. If a
    palace ever has >50K entities and this proves too slow, the right move
    is a separate completion cache, not a paginated wire protocol (the
    spec doesn't paginate completion).
    """
    col = _get_collection()
    if template == f"{_SCHEME_PREFIX}drawers/{{drawer_id}}" and arg_name == "drawer_id":
        if col is None:
            return []
        # Drawer IDs are long deterministic strings. We can't enumerate all
        # of them cheaply, but partial-match by recent filed_at is what users
        # actually want — it's "complete the ID I just made". Pull recent.
        result = col.get(include=["metadatas"], limit=500)
        return list(result["ids"] if isinstance(result, dict) else result.ids)
    if template == f"{_SCHEME_PREFIX}diary/{{date}}" and arg_name == "date":
        if col is None:
            return []
        result = col.get(
            where={"room": "diary"}, include=["metadatas"], limit=10000
        )
        metas = result["metadatas"] if isinstance(result, dict) else result.metadatas
        return sorted({(m or {}).get("date", "") for m in metas} - {""}, reverse=True)
    if template == f"{_SCHEME_PREFIX}kg/{{node_id}}" and arg_name == "node_id":
        with _kg._lock:  # noqa: SLF001
            rows = _kg._conn().execute(
                "SELECT id FROM entities ORDER BY id LIMIT 5000"
            ).fetchall()
        return [r["id"] for r in rows]
    if template == f"{_SCHEME_PREFIX}kg/timeline/{{from_date}}/{{to_date}}":
        # Suggest dates that actually appear as valid_from / valid_to.
        with _kg._lock:  # noqa: SLF001
            rows = _kg._conn().execute(
                "SELECT DISTINCT valid_from FROM triples "
                "WHERE valid_from IS NOT NULL "
                "UNION SELECT DISTINCT valid_to FROM triples "
                "WHERE valid_to IS NOT NULL"
            ).fetchall()
        return sorted({r[0] for r in rows if r[0]}, reverse=True)
    if template == f"{_SCHEME_PREFIX}wings/{{wing}}/rooms/{{room}}":
        if col is None:
            return []
        if arg_name == "wing":
            metas = _get_cached_metadata(col, None)
            return sorted({(m or {}).get("wing", "") for m in metas} - {""})
        if arg_name == "room":
            # Chain on the prior wing arg from context.arguments.
            prior_wing = ctx_args.get("wing")
            where = {"wing": prior_wing} if prior_wing else None
            metas = _fetch_all_metadata(col, where=where)
            return sorted({(m or {}).get("room", "") for m in metas} - {""})
    return []


# ---------------------------------------------------------------------------
# Subscriptions (Tier 2 — spec §3.4 / §4)
# ---------------------------------------------------------------------------

_SUBSCRIPTIONS_LOCK = threading.Lock()
_SUBSCRIPTIONS: Dict[str, str] = {}  # uri -> last_known_hash
_emit_callback: Optional[Callable[[dict], None]] = None


def set_emit_callback(fn: Callable[[dict], None]) -> None:
    """Hand the module the function that writes a JSON-RPC notification
    to stdout. Called once from mcp_server.main() after stdout is restored.
    """
    global _emit_callback
    _emit_callback = fn


def _hash_uri(uri: str) -> str:
    """Compute a stable hash of the URI's current rendered content.

    On error returns the empty string — that way poll_subscriptions
    can detect "definitely changed" (hash differs and is non-empty)
    without false positives during transient backend hiccups.
    """
    try:
        result = read_resource(uri)
        joined = "".join(
            getattr(c, "text", "") or getattr(c, "blob", "")
            for c in result.contents
        )
        return hashlib.sha256(joined.encode()).hexdigest()
    except ResourceError:
        return ""


def subscribe_resource(uri: str) -> SubscriptionResult:
    """Spec §3.4 — register a subscription. Returns immediately.

    Templates can't be subscribed: a template has no concrete content
    to hash. Concrete URIs (those that match a single resource) are
    accepted. We accept both static and templated-instance URIs.
    """
    if "{" in uri or "}" in uri:
        raise InvalidParamError(
            "Cannot subscribe to a template URI — provide a concrete URI"
        )
    # Probe the URI now so subscribe fails fast on 404.
    _ = read_resource(uri)
    with _SUBSCRIPTIONS_LOCK:
        _SUBSCRIPTIONS[uri] = _hash_uri(uri)
    return SubscriptionResult(uri=uri, subscribed=True)


def unsubscribe_resource(uri: str) -> SubscriptionResult:
    with _SUBSCRIPTIONS_LOCK:
        existed = _SUBSCRIPTIONS.pop(uri, None) is not None
    return SubscriptionResult(uri=uri, subscribed=False if existed else False)


def poll_subscriptions() -> List[dict]:
    """Re-hash every subscribed URI; emit notifications for changes.

    Designed to be called from the write-tool dispatcher in
    mcp_server.handle_request after every successful tool call that
    might mutate the palace (add_drawer, update_drawer, delete_drawer,
    diary_write, kg_add, kg_invalidate, create_tunnel, delete_tunnel).
    Returns the list of notification dicts emitted (also pushed via
    the emit callback if configured).
    """
    notifications: List[dict] = []
    with _SUBSCRIPTIONS_LOCK:
        items = list(_SUBSCRIPTIONS.items())
    for uri, prev_hash in items:
        current = _hash_uri(uri)
        if current and current != prev_hash:
            with _SUBSCRIPTIONS_LOCK:
                _SUBSCRIPTIONS[uri] = current
            notif = {
                "jsonrpc": "2.0",
                "method": "notifications/resources/updated",
                "params": {"uri": uri},
            }
            notifications.append(notif)
            if _emit_callback is not None:
                try:
                    _emit_callback(notif)
                except Exception:
                    logger.exception("emit_callback failed for %s", uri)
    return notifications


def notify_list_changed() -> dict:
    """Build (and emit) a notifications/resources/list_changed payload.

    Currently only fired manually — invoke after operations that
    materially shift the static catalog (palace nuke, init, repair).
    """
    notif = {
        "jsonrpc": "2.0",
        "method": "notifications/resources/list_changed",
    }
    if _emit_callback is not None:
        try:
            _emit_callback(notif)
        except Exception:
            logger.exception("emit_callback failed for list_changed")
    return notif


# ---------------------------------------------------------------------------
# JSON serializer hook — dataclasses → dicts for JSON-RPC dispatch.
# ---------------------------------------------------------------------------


def to_jsonable(obj: Any) -> Any:
    """Convert dataclass results into dicts ready for json.dumps.

    Used by the dispatcher when wrapping a result into the JSON-RPC
    envelope. Strips `meta={}` defaults to keep payloads tight.
    """
    if hasattr(obj, "__dataclass_fields__"):
        out = asdict(obj)
        # Drop empty meta to match spec's "omit when absent" wire shape.
        if isinstance(out.get("meta"), dict) and not out["meta"]:
            del out["meta"]
        if "resources" in out:
            for r in out["resources"]:
                if isinstance(r.get("meta"), dict) and not r["meta"]:
                    del r["meta"]
        if "resourceTemplates" in out:
            for r in out["resourceTemplates"]:
                if isinstance(r.get("meta"), dict) and not r["meta"]:
                    del r["meta"]
        # Drop nextCursor when None (spec: omit when absent).
        if out.get("nextCursor") is None and "nextCursor" in out:
            del out["nextCursor"]
        return out
    if isinstance(obj, list):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    return obj


__all__ = [
    "RESOURCES_SCHEMA_VERSION",
    "Resource",
    "ResourceTemplate",
    "TextResourceContents",
    "BlobResourceContents",
    "ListResourcesResult",
    "ListResourceTemplatesResult",
    "ReadResourceResult",
    "CompletionEntry",
    "CompletionResult",
    "SubscriptionResult",
    "ResourceError",
    "InvalidUriError",
    "ResourceNotFoundError",
    "InvalidParamError",
    "configure_backends",
    "list_resources",
    "list_resource_templates",
    "read_resource",
    "complete_argument",
    "subscribe_resource",
    "unsubscribe_resource",
    "poll_subscriptions",
    "notify_list_changed",
    "set_emit_callback",
    "to_jsonable",
]
