"""Domain errors and the uniform API error format."""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from django.utils import translation
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from core.middleware import get_request_id

logger = logging.getLogger(__name__)

# code -> (Arabic, English)
MESSAGES: dict[str, tuple[str, str]] = {
    "validation_error": ("البيانات المدخلة غير صحيحة", "Invalid input"),
    "not_found": ("غير موجود", "Not found"),
    "permission_denied": ("ما عندك صلاحية لهذا الإجراء", "You do not have permission"),
    "not_authenticated": ("لازم تسجل دخول", "Authentication required"),
    "throttled": ("طلبات كثيرة، حاول بعد شوية", "Too many requests, try again later"),
    "conflict": ("تم تحديث البيانات من مكان ثاني", "The resource was modified concurrently"),
    "product_unavailable": ("هذا المنتج غير متوفر حالياً", "This product is not available"),
    "insufficient_stock": ("الكمية المطلوبة غير متوفرة", "Not enough stock"),
    "invalid_options": ("الخيارات المختارة غير صحيحة", "Invalid product options"),
    "cart_empty": ("السلة فارغة", "Your cart is empty"),
    "below_minimum_order": ("الطلب أقل من الحد الأدنى", "Order is below the minimum amount"),
    "outside_working_hours": ("المحل مسكّر هسه", "The business is closed right now"),
    "business_unavailable": ("المحل غير متاح حالياً", "This business is not available"),
    "fulfilment_unavailable": ("طريقة الاستلام هذي غير متاحة", "Fulfilment type not available"),
    "delivery_zone_required": ("اختار منطقة التوصيل", "Choose a delivery zone"),
    "delivery_zone_invalid": ("منطقة التوصيل غير صحيحة", "Invalid delivery zone"),
    "address_required": ("اكتب عنوان التوصيل", "Delivery address is required"),
    "invalid_phone": ("رقم الهاتف غير صحيح", "Invalid phone number"),
    "payment_method_unavailable": ("طريقة الدفع غير متاحة", "Payment method not available"),
    "customer_blocked": ("ما تكدر تطلب من هذا المحل", "You cannot order from this business"),
    "too_many_open_orders": ("عندك طلبات مفتوحة كثيرة", "Too many open orders"),
    "invalid_transition": ("ما يصير تغيير حالة الطلب لهذي الحالة", "Invalid status change"),
    "stale_order_version": ("الطلب تحدّث من شخص ثاني", "Order was already updated"),
    "cancel_window_expired": ("انتهى وقت إلغاء الطلب", "The cancellation window has expired"),
    "reason_required": ("لازم تكتب السبب", "A reason is required"),
    "plan_limit_exceeded": ("وصلت للحد المسموح بخطتك", "Your plan limit has been reached"),
    "feature_not_available": ("هذي الميزة مو ضمن خطتك", "Feature not included in your plan"),
    "idempotency_key_required": ("مفتاح التكرار مطلوب", "Idempotency-Key header is required"),
    "invalid_init_data": ("بيانات تيليجرام غير صالحة", "Invalid Telegram init data"),
    "invalid_bot_token": ("توكن البوت غير صحيح", "Invalid bot token"),
    "telegram_error": ("خطأ بالاتصال بتيليجرام", "Telegram API error"),
    "invalid_link_code": ("الكود غير صحيح أو منتهي", "Invalid or expired code"),
    "owner_role_protected": ("ما يصير تعديل دور المالك", "The owner role cannot be changed"),
    "last_owner": ("لازم يبقى مالك واحد على الأقل", "A business needs at least one owner"),
    "invalid_credentials": ("بيانات الدخول غير صحيحة", "Invalid credentials"),
    "otp_required": ("أدخل رمز التحقق", "Two-factor code required"),
    "invalid_otp": ("رمز التحقق غير صحيح", "Invalid two-factor code"),
    "invalid_image": ("الصورة غير صالحة", "Invalid image"),
    "coupon_invalid": ("كود الخصم غير صحيح", "Invalid coupon code"),
    "coupon_expired": ("كود الخصم منتهي", "This coupon has expired"),
    "coupon_min_order": (
        "الطلب أقل من الحد الأدنى لهذا الكود",
        "Order is below this coupon's minimum",
    ),
    "coupon_exhausted": ("كود الخصم مستخدم بالكامل", "This coupon has been used up"),
    "ai_unavailable": ("المساعد الذكي غير متاح حالياً", "The AI assistant is unavailable"),
}


def message_for(code: str, lang: str | None = None) -> str:
    lang = lang or translation.get_language() or "ar"
    ar, en = MESSAGES.get(code, (code, code))
    return en if lang.startswith("en") else ar


class DomainError(Exception):
    """A business-rule violation. Raised by services; rendered by the API layer."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(
        self, code: str, details: dict[str, Any] | None = None, status_code: int | None = None
    ):
        super().__init__(code)
        self.code = code
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code

    @property
    def message(self) -> str:
        return message_for(self.code)


class ConflictError(DomainError):
    status_code = status.HTTP_409_CONFLICT


class NotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, details: dict[str, Any] | None = None):
        super().__init__("not_found", details)


class ForbiddenError(DomainError):
    status_code = status.HTTP_403_FORBIDDEN

    def __init__(self, details: dict[str, Any] | None = None):
        super().__init__("permission_denied", details)


def error_body(code: str, details: Any = None, message: str | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message or message_for(code),
            "details": details or {},
            "request_id": get_request_id(),
        }
    }


_DRF_CODES = {
    exceptions.NotAuthenticated: "not_authenticated",
    exceptions.AuthenticationFailed: "not_authenticated",
    exceptions.PermissionDenied: "permission_denied",
    exceptions.NotFound: "not_found",
    exceptions.Throttled: "throttled",
    exceptions.ValidationError: "validation_error",
    exceptions.ParseError: "validation_error",
}


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, DomainError):
        return Response(error_body(exc.code, exc.details), status=exc.status_code)
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled API error", exc_info=exc)
        return None

    code = next((c for cls, c in _DRF_CODES.items() if isinstance(exc, cls)), None)
    if code is None:
        code = getattr(exc, "default_code", "error")
    details: Any = response.data if code == "validation_error" else {}
    if isinstance(details, list):  # a bare field's run_validation(): keep `details` an object
        details = {"non_field_errors": details}
    if isinstance(exc, exceptions.Throttled) and exc.wait:
        details = {"retry_after": int(exc.wait)}
    response.data = error_body(code, details)
    return response
