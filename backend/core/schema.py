"""drf-spectacular integration: auth schemes and the scope of the public OpenAPI document."""

from __future__ import annotations

from typing import Any

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class CustomerTokenScheme(OpenApiAuthenticationExtension):
    target_class = "apps.storefront.auth.CustomerTokenAuthentication"
    name = "customerToken"

    def get_security_definition(self, auto_schema: Any) -> dict[str, str]:
        return {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": "`Customer <token>` from POST /store/{slug}/session (Telegram initData)",
        }


def public_endpoints_only(endpoints: list[tuple[Any, ...]], **_: Any) -> list[tuple[Any, ...]]:
    """/internal/v1 is the bot service's private API on the internal network: never published."""
    return [e for e in endpoints if e[0].startswith("/api/")]


ERROR_SCHEMA = {
    "type": "object",
    "description": "Every 4xx/5xx response uses this envelope (core.errors).",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Stable machine-readable code"},
                "message": {"type": "string", "description": "Localised (Accept-Language)"},
                "details": {"type": "object", "additionalProperties": {}},
                "request_id": {"type": "string"},
            },
            "required": ["code", "message", "details", "request_id"],
        }
    },
    "required": ["error"],
}


def error_envelope(result: dict[str, Any], **_: Any) -> dict[str, Any]:
    """Documents the shared error envelope as the 4XX response of every operation."""
    result.setdefault("components", {}).setdefault("schemas", {})["Error"] = ERROR_SCHEMA
    ref = {"$ref": "#/components/schemas/Error"}
    for item in result.get("paths", {}).values():
        for op in item.values():
            if isinstance(op, dict) and "responses" in op:
                op["responses"].setdefault(
                    "4XX",
                    {"description": "Error", "content": {"application/json": {"schema": ref}}},
                )
    return result


def responses_fully_required(result: dict[str, Any], **_: Any) -> dict[str, Any]:
    """DRF always serialises every readable field, so response objects have all their keys.

    drf-spectacular marks fields with model defaults as optional, which would make every client
    type `T | undefined`. Request components (`*Request`, split by COMPONENT_SPLIT_REQUEST) keep
    their real optionality. tests/test_openapi.py checks real responses contain every key.
    """
    for name, component in result.get("components", {}).get("schemas", {}).items():
        if name.endswith("Request") or "properties" not in component:
            continue
        component["required"] = sorted(component["properties"])
    return result
