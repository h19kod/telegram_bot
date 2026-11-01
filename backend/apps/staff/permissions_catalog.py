"""The fixed permission catalog. Roles are configurable sets of these codenames."""

from __future__ import annotations

PERMISSIONS: dict[str, str] = {
    "orders.view": "View orders",
    "orders.view_assigned_only": "Only see orders assigned to me",
    "orders.receive_notifications": "Receive new order notifications",
    "orders.transition.confirmed": "Accept orders",
    "orders.transition.rejected": "Reject orders",
    "orders.transition.preparing": "Start preparing",
    "orders.transition.ready": "Mark ready",
    "orders.transition.out_for_delivery": "Mark out for delivery",
    "orders.transition.delivered": "Mark delivered",
    "orders.cancel": "Cancel orders",
    "orders.assign_driver": "Assign delivery staff",
    "catalog.view": "View catalog",
    "catalog.edit": "Edit catalog",
    "catalog.edit_prices": "Edit prices and discounts",
    "customers.view": "View customers",
    "customers.view_pii": "View customer phone numbers and addresses",
    "customers.block": "Block customers",
    "staff.manage": "Manage staff and roles",
    "delivery.manage": "Manage delivery zones",
    "reports.view": "View reports",
    "reports.export": "Export reports",
    "settings.edit": "Edit business settings",
    "telegram.edit": "Edit Telegram settings",
    "billing.manage": "Manage subscription",
    "ai.manage": "Manage AI assistant and conversations",
}

_ALL = set(PERMISSIONS) - {"orders.view_assigned_only"}
_TRANSITIONS_ALL = {p for p in PERMISSIONS if p.startswith("orders.transition.")}

DEFAULT_ROLES: dict[str, dict[str, object]] = {
    "Owner": {"is_owner": True, "permissions": _ALL},
    "Manager": {
        "is_owner": False,
        "permissions": _ALL - {"billing.manage", "telegram.edit"},
    },
    "Cashier": {
        "is_owner": False,
        "permissions": {
            "orders.view",
            "orders.receive_notifications",
            "catalog.view",
            "customers.view",
            "customers.view_pii",
            *_TRANSITIONS_ALL,
        },
    },
    "Kitchen": {
        "is_owner": False,
        "permissions": {
            "orders.view",
            "orders.receive_notifications",
            "orders.transition.preparing",
            "orders.transition.ready",
            "catalog.view",
        },
    },
    "Delivery": {
        "is_owner": False,
        "permissions": {
            "orders.view",
            "orders.view_assigned_only",
            "orders.receive_notifications",
            "orders.transition.out_for_delivery",
            "orders.transition.delivered",
            "customers.view_pii",
        },
    },
}
