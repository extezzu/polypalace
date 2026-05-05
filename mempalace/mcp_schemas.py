"""
JSON Schemas for tool outputs (MCP spec 2025-06-18+ outputSchema feature).

Each entry в OUTPUT_SCHEMAS describes the success-shape of the tool's return
value. When attached to a tool definition, the server emits `outputSchema` в
`tools/list` and `structuredContent` (the raw result dict) on `tools/call`.

Source-of-truth: `data/research/polypalace-implementation/phase1/output-schemas.md`.
Validation is opt-in via `POLYPALACE_VALIDATE_OUTPUT=1` (uses jsonschema).
"""

# Shared $defs available across schemas (referenced via #/$defs/<name>)
_SHARED_DEFS = {
    "DrawerMetadata": {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "wing": {"type": "string"},
            "room": {"type": "string"},
            "source_file": {"type": ["string", "null"]},
            "chunk_index": {"type": ["integer", "null"]},
            "added_by": {"type": ["string", "null"]},
            "filed_at": {"type": ["string", "null"]},
        },
    },
    "ErrorEnvelope": {
        "type": "object",
        "properties": {
            "error": {"type": "string"},
            "hint": {"type": "string"},
        },
        "required": ["error"],
    },
}


def _with_defs(schema):
    """Attach shared $defs to a schema so #/$defs/* references resolve."""
    out = dict(schema)
    out["$defs"] = _SHARED_DEFS
    return out


OUTPUT_SCHEMAS = {
    "mempalace_status": _with_defs({
        "type": "object",
        "required": ["total_drawers", "wings", "rooms", "palace_path", "protocol", "aaak_dialect"],
        "properties": {
            "total_drawers": {"type": "integer", "minimum": 0},
            "wings": {
                "type": "object",
                "additionalProperties": {"type": "integer", "minimum": 0},
            },
            "rooms": {
                "type": "object",
                "additionalProperties": {"type": "integer", "minimum": 0},
            },
            "palace_path": {"type": "string"},
            "protocol": {"type": "string"},
            "aaak_dialect": {"type": "string"},
            "vector_disabled": {"type": "boolean"},
            "vector_disabled_reason": {"type": "string"},
            "hnsw_capacity": {
                "type": "object",
                "properties": {
                    "sqlite_count": {"type": "integer"},
                    "hnsw_count": {"type": "integer"},
                    "divergence": {"type": "integer"},
                },
            },
            "error": {"type": "string"},
            "partial": {"type": "boolean"},
        },
    }),

    "mempalace_search": _with_defs({
        "type": "object",
        "oneOf": [
            {
                "type": "object",
                "required": ["query", "results"],
                "properties": {
                    "query": {"type": "string"},
                    "filters": {
                        "type": "object",
                        "properties": {
                            "wing": {"type": ["string", "null"]},
                            "room": {"type": ["string", "null"]},
                        },
                    },
                    "total_before_filter": {"type": "integer", "minimum": 0},
                    "results": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["text", "wing", "room", "matched_via"],
                            "properties": {
                                "text": {"type": "string"},
                                "wing": {"type": "string"},
                                "room": {"type": "string"},
                                "drawer_id": {"type": ["string", "null"]},
                                "distance": {"type": ["number", "null"]},
                                "similarity": {"type": ["number", "null"]},
                                "matched_via": {"type": "string"},
                                "drawer_index": {"type": ["integer", "null"]},
                                "total_drawers": {"type": ["integer", "null"]},
                            },
                        },
                    },
                    "vector_disabled": {"type": "boolean"},
                    "vector_disabled_reason": {"type": "string"},
                    "query_sanitized": {"type": "boolean"},
                    "context_received": {"type": "boolean"},
                },
            },
            {"$ref": "#/$defs/ErrorEnvelope"},
        ],
    }),

    "mempalace_kg_query": {
        "type": "object",
        "required": ["entity", "facts", "count"],
        "properties": {
            "entity": {"type": "string"},
            "as_of": {"type": ["string", "null"]},
            "count": {"type": "integer", "minimum": 0},
            "facts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["direction", "subject", "predicate", "object", "current"],
                    "properties": {
                        "direction": {"type": "string", "enum": ["outgoing", "incoming"]},
                        "subject": {"type": "string"},
                        "predicate": {"type": "string"},
                        "object": {"type": "string"},
                        "valid_from": {"type": ["string", "null"]},
                        "valid_to": {"type": ["string", "null"]},
                        "confidence": {"type": ["number", "null"]},
                        "source_closet": {"type": ["string", "null"]},
                        "current": {"type": "boolean"},
                    },
                },
            },
        },
    },

    "mempalace_kg_timeline": {
        "type": "object",
        "required": ["entity", "timeline", "count"],
        "properties": {
            "entity": {"type": "string"},
            "count": {"type": "integer", "minimum": 0},
            "timeline": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["subject", "predicate", "object", "current"],
                    "properties": {
                        "subject": {"type": "string"},
                        "predicate": {"type": "string"},
                        "object": {"type": "string"},
                        "valid_from": {"type": ["string", "null"]},
                        "valid_to": {"type": ["string", "null"]},
                        "current": {"type": "boolean"},
                    },
                },
            },
        },
    },

    "mempalace_kg_stats": {
        "type": "object",
        "required": ["entities", "triples", "current_facts", "expired_facts", "relationship_types"],
        "properties": {
            "entities": {"type": "integer", "minimum": 0},
            "triples": {"type": "integer", "minimum": 0},
            "current_facts": {"type": "integer", "minimum": 0},
            "expired_facts": {"type": "integer", "minimum": 0},
            "relationship_types": {"type": "array", "items": {"type": "string"}},
        },
    },

    "mempalace_get_drawer": _with_defs({
        "type": "object",
        "oneOf": [
            {
                "type": "object",
                "required": ["drawer_id", "content", "wing", "room", "metadata"],
                "properties": {
                    "drawer_id": {"type": "string"},
                    "content": {"type": "string"},
                    "wing": {"type": "string"},
                    "room": {"type": "string"},
                    "metadata": {"$ref": "#/$defs/DrawerMetadata"},
                },
            },
            {"$ref": "#/$defs/ErrorEnvelope"},
        ],
    }),

    "mempalace_list_drawers": _with_defs({
        "type": "object",
        "oneOf": [
            {
                "type": "object",
                "required": ["drawers", "count", "offset", "limit"],
                "properties": {
                    "drawers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["drawer_id", "wing", "room", "content_preview"],
                            "properties": {
                                "drawer_id": {"type": "string"},
                                "wing": {"type": "string"},
                                "room": {"type": "string"},
                                "content_preview": {"type": "string"},
                            },
                        },
                    },
                    "count": {"type": "integer", "minimum": 0},
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1},
                },
            },
            {"$ref": "#/$defs/ErrorEnvelope"},
        ],
    }),

    # find_tunnels and follow_tunnels return arrays. We expose them as
    # array-typed structuredContent. Older clients that expect object
    # structuredContent will gracefully fall back to text content (which is
    # always present).
    "mempalace_find_tunnels": {
        "type": "array",
        "items": {
            "type": "object",
            "required": ["room", "wings", "count"],
            "properties": {
                "room": {"type": "string"},
                "wings": {"type": "array", "items": {"type": "string"}},
                "halls": {"type": "array", "items": {"type": "string"}},
                "count": {"type": "integer", "minimum": 1},
                "recent": {"type": "string"},
            },
        },
    },

    "mempalace_follow_tunnels": {
        "type": "array",
        "items": {
            "type": "object",
            "required": ["direction", "connected_wing", "connected_room", "tunnel_id"],
            "properties": {
                "direction": {"type": "string", "enum": ["outgoing", "incoming"]},
                "connected_wing": {"type": "string"},
                "connected_room": {"type": "string"},
                "label": {"type": "string"},
                "drawer_id": {"type": ["string", "null"]},
                "drawer_preview": {"type": "string"},
                "tunnel_id": {"type": "string"},
            },
        },
    },

    "mempalace_diary_read": _with_defs({
        "type": "object",
        "oneOf": [
            {
                "type": "object",
                "required": ["agent", "entries"],
                "properties": {
                    "agent": {"type": "string"},
                    "entries": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["date", "timestamp", "topic", "content"],
                            "properties": {
                                "date": {"type": "string"},
                                "timestamp": {"type": "string"},
                                "topic": {"type": "string"},
                                "content": {"type": "string"},
                            },
                        },
                    },
                    "total": {"type": "integer", "minimum": 0},
                    "showing": {"type": "integer", "minimum": 0},
                    "message": {"type": "string"},
                },
            },
            {"$ref": "#/$defs/ErrorEnvelope"},
        ],
    }),
}
