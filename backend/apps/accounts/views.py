from __future__ import annotations

import contextlib
import secrets

from django.conf import settings
from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services
from apps.accounts.models import User
from apps.accounts.serializers import (
    LoginSerializer,
    MembershipSerializer,
    OtpSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetSerializer,
    RegisterSerializer,
    UserSerializer,
)
from apps.staff.models import Membership
from apps.staff.services import accept_invitation
from core.errors import DomainError

CSRF_COOKIE = "sop_csrf"
COOKIE_PATH = "/api/v1/auth/"

TOKEN_RESPONSE = inline_serializer(
    "TokenResponse",
    {
        "access": serializers.CharField(help_text="JWT access token (Authorization: Bearer)"),
        "user": UserSerializer(),
    },
)
CSRF_HEADER = OpenApiParameter(
    "X-CSRF-Token",
    str,
    OpenApiParameter.HEADER,
    required=True,
    description="Value of the sop_csrf cookie (double-submit); refresh token comes from its cookie",
)


def _expiring(name: str, field: str) -> serializers.Serializer:
    return inline_serializer(
        name, {field: serializers.CharField(), "expires_in": serializers.IntegerField()}
    )


def _token_response(user: User, refresh: RefreshToken, code: int = 200) -> Response:
    resp = Response(
        {"access": str(refresh.access_token), "user": UserSerializer(user).data}, status=code
    )
    csrf = secrets.token_urlsafe(24)
    max_age = int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())
    resp.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        str(refresh),
        max_age=max_age,
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite="Strict",
        path=COOKIE_PATH,
    )
    resp.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=max_age,
        httponly=False,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite="Strict",
        path="/",
    )
    return resp


class LoginThrottle(ScopedRateThrottle):
    scope_attr = "throttle_scope"


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [LoginThrottle]
    throttle_scope = "login"

    @extend_schema(request=RegisterSerializer, responses={201: TOKEN_RESPONSE})
    def post(self, request: Request) -> Response:
        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            user = services.register(**s.validated_data)
        except password_validation.ValidationError as exc:
            raise DomainError("validation_error", {"password": exc.messages}, 400) from None
        return _token_response(user, RefreshToken.for_user(user), 201)


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [LoginThrottle]
    throttle_scope = "login"

    @extend_schema(request=LoginSerializer, responses=TOKEN_RESPONSE)
    def post(self, request: Request) -> Response:
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = authenticate(
            request, username=s.validated_data["identifier"], password=s.validated_data["password"]
        )
        if user is None:
            raise DomainError("invalid_credentials", status_code=401)
        if user.totp_enabled:
            otp = s.validated_data.get("otp")
            if not otp:
                raise DomainError("otp_required", status_code=401)
            if not services.verify_totp(user, otp):
                raise DomainError("invalid_otp", status_code=401)
        return _token_response(user, RefreshToken.for_user(user))


class RefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(request=None, parameters=[CSRF_HEADER], responses=TOKEN_RESPONSE)
    def post(self, request: Request) -> Response:
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        csrf_cookie = request.COOKIES.get(CSRF_COOKIE, "")
        csrf_header = request.headers.get("X-CSRF-Token", "")
        if not raw or not csrf_cookie or not secrets.compare_digest(csrf_cookie, csrf_header):
            raise DomainError("not_authenticated", status_code=401)
        try:
            old = RefreshToken(raw)
            user = User.objects.get(pk=old["user_id"], is_active=True)
            old.blacklist()
        except (TokenError, User.DoesNotExist):
            raise DomainError("not_authenticated", status_code=401) from None
        return _token_response(user, RefreshToken.for_user(user))


class LogoutView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if raw:
            with contextlib.suppress(TokenError):
                RefreshToken(raw).blacklist()
        resp = Response(status=status.HTTP_204_NO_CONTENT)
        resp.delete_cookie(settings.REFRESH_COOKIE_NAME, path=COOKIE_PATH)
        resp.delete_cookie(CSRF_COOKIE, path="/")
        return resp


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UserSerializer)
    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data)

    @extend_schema(request=UserSerializer, responses=UserSerializer)
    def patch(self, request: Request) -> Response:
        s = UserSerializer(request.user, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)


class MyMembershipsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MembershipSerializer(many=True))
    def get(self, request: Request) -> Response:
        qs = Membership.objects.select_related("business", "role").filter(
            user=request.user, is_active=True
        )
        return Response(MembershipSerializer(qs, many=True).data)


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=PasswordChangeSerializer, responses=None)
    def post(self, request: Request) -> Response:
        s = PasswordChangeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            services.change_password(
                request.user, s.validated_data["old_password"], s.validated_data["new_password"]
            )
        except password_validation.ValidationError as exc:
            raise DomainError("validation_error", {"new_password": exc.messages}, 400) from None
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [LoginThrottle]
    throttle_scope = "login"

    @extend_schema(request=PasswordResetSerializer, responses=None)
    def post(self, request: Request) -> Response:
        s = PasswordResetSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=s.validated_data["email"], is_active=True).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            link = f"{settings.DASHBOARD_BASE_URL}/reset-password?uid={uid}&token={token}"
            send_mail(
                "Reset your password",
                f"Open this link to reset your password:\n{link}",
                None,
                [user.email],
                fail_silently=True,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)  # same response either way


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(request=PasswordResetConfirmSerializer, responses=None)
    def post(self, request: Request) -> Response:
        s = PasswordResetConfirmSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(s.validated_data["uid"])))
        except (User.DoesNotExist, ValueError, TypeError):
            raise DomainError("invalid_link_code", status_code=400) from None
        if not default_token_generator.check_token(user, s.validated_data["token"]):
            raise DomainError("invalid_link_code", status_code=400)
        try:
            password_validation.validate_password(s.validated_data["new_password"], user)
        except password_validation.ValidationError as exc:
            raise DomainError("validation_error", {"new_password": exc.messages}, 400) from None
        user.set_password(s.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        services.revoke_all_tokens(user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TotpSetupView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses=inline_serializer("TotpSetup", {"provisioning_uri": serializers.CharField()}),
    )
    def post(self, request: Request) -> Response:
        return Response({"provisioning_uri": services.totp_setup(request.user)})


class TotpEnableView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=OtpSerializer, responses=None)
    def post(self, request: Request) -> Response:
        s = OtpSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.totp_enable(request.user, s.validated_data["otp"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class TotpDisableView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=OtpSerializer, responses=None)
    def post(self, request: Request) -> Response:
        s = OtpSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.totp_disable(request.user, s.validated_data["otp"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class TelegramLinkCodeView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [LoginThrottle]
    throttle_scope = "link_code"

    @extend_schema(request=None, responses=_expiring("TelegramLinkCode", "code"))
    def post(self, request: Request) -> Response:
        return Response({"code": services.create_link_code(request.user), "expires_in": 600})

    @extend_schema(responses={204: None})
    def delete(self, request: Request) -> Response:
        from apps.accounts.models import TelegramAccount

        TelegramAccount.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WsTicketView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=_expiring("WsTicket", "ticket"))
    def post(self, request: Request) -> Response:
        return Response(
            {"ticket": services.issue_ws_ticket(request.user), "expires_in": services.WS_TICKET_TTL}
        )


class AcceptInvitationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={201: MembershipSerializer})
    def post(self, request: Request, token: str) -> Response:
        membership = accept_invitation(token, request.user)
        return Response(MembershipSerializer(membership).data, status=201)
