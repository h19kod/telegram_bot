from __future__ import annotations

from typing import Any

from django.conf import settings
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.platform_admin.audit import audit
from apps.staff import services
from apps.staff.models import Membership, Permission, Role, StaffInvitation
from apps.staff.permissions_catalog import PERMISSIONS
from core.errors import DomainError
from core.tenancy import IsBusinessMember, TenantPrimaryKeyRelatedField, TenantViewSet


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.ListField(
        child=serializers.ChoiceField(choices=list(PERMISSIONS)), required=False, write_only=True
    )
    members_count = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ["id", "name", "is_owner", "is_system", "permissions", "members_count"]
        read_only_fields = ["id", "is_owner", "is_system"]

    def to_representation(self, instance: Role) -> dict[str, Any]:
        data = super().to_representation(instance)
        data["permissions"] = sorted(instance.permissions.values_list("codename", flat=True))
        return data

    def get_members_count(self, obj: Role) -> int:
        return obj.memberships.filter(is_active=True).count()


class RoleViewSet(TenantViewSet):
    model = Role
    serializer_class = RoleSerializer
    required_permissions = {"*": ["staff.manage"]}
    pagination_class = None

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        perms = serializer.validated_data.pop("permissions", [])
        role = serializer.save(business=self.business)
        role.permissions.set(Permission.objects.filter(codename__in=perms))
        audit(self.request, "role.create", self.business, role, {"permissions": perms})

    def perform_update(self, serializer: serializers.BaseSerializer) -> None:
        services.update_role(
            serializer.instance,
            serializer.validated_data.get("name"),
            serializer.validated_data.get("permissions"),
        )
        audit(
            self.request,
            "role.update",
            self.business,
            serializer.instance,
            dict(serializer.validated_data),
        )

    def perform_destroy(self, instance: Role) -> None:
        if instance.is_owner:
            raise DomainError("owner_role_protected", status_code=403)
        if instance.memberships.filter(is_active=True).exists():
            raise DomainError("validation_error", {"role": ["role has members"]}, 400)
        audit(self.request, "role.delete", self.business, instance)
        instance.delete()


class PermissionListView(APIView):
    permission_classes = [IsBusinessMember]

    def get(self, request: Request, business_id: Any) -> Response:
        return Response([{"codename": k, "description": v} for k, v in PERMISSIONS.items()])


class MemberSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    has_telegram = serializers.SerializerMethodField()
    role = TenantPrimaryKeyRelatedField(queryset=Role.objects.all())
    role_name = serializers.CharField(source="role.name", read_only=True)

    class Meta:
        model = Membership
        fields = [
            "id",
            "email",
            "phone",
            "full_name",
            "role",
            "role_name",
            "is_active",
            "has_telegram",
            "created_at",
        ]
        read_only_fields = ["id", "is_active", "created_at"]

    def get_has_telegram(self, obj: Membership) -> bool:
        return hasattr(obj.user, "telegram")


class MemberViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsBusinessMember]
    serializer_class = MemberSerializer
    required_permissions = {
        "list": ["staff.manage"],
        "retrieve": ["staff.manage"],
        "write": ["staff.manage"],
        "drivers": ["orders.assign_driver"],
    }
    http_method_names = ["get", "patch", "delete"]
    pagination_class = None

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return (
            Membership.objects.for_business(self.request.business)
            .select_related("user", "role", "user__telegram")
            .filter(is_active=True)
        )

    def get_serializer_context(self) -> dict[str, Any]:
        ctx = super().get_serializer_context()
        ctx["business"] = getattr(self.request, "business", None)
        return ctx

    def perform_update(self, serializer: serializers.BaseSerializer) -> None:
        role = serializer.validated_data.get("role")
        if role is not None:
            services.change_member_role(serializer.instance, role, self.request.membership)
            audit(
                self.request,
                "member.role_change",
                self.request.business,
                serializer.instance,
                {"role": role.name},
            )

    def perform_destroy(self, instance: Membership) -> None:
        services.deactivate_member(instance, self.request.membership)
        audit(self.request, "member.remove", self.request.business, instance)

    @action(detail=False, methods=["get"])
    def drivers(self, request: Request, business_id: Any) -> Response:
        qs = (
            self.get_queryset()
            .filter(role__permissions__codename="orders.transition.delivered")
            .distinct()
        )
        return Response(MemberSerializer(qs, many=True, context=self.get_serializer_context()).data)


class InvitationSerializer(serializers.ModelSerializer):
    role = TenantPrimaryKeyRelatedField(queryset=Role.objects.all())
    accept_url = serializers.SerializerMethodField()

    class Meta:
        model = StaffInvitation
        fields = [
            "id",
            "email",
            "phone",
            "role",
            "expires_at",
            "accepted_at",
            "created_at",
            "accept_url",
        ]
        read_only_fields = ["id", "expires_at", "accepted_at", "created_at"]

    def get_accept_url(self, obj: StaffInvitation) -> str | None:
        token = getattr(obj, "_token", None)
        return f"{settings.DASHBOARD_BASE_URL}/invite/{token}" if token else None


class InvitationViewSet(TenantViewSet):
    model = StaffInvitation
    serializer_class = InvitationSerializer
    required_permissions = {"*": ["staff.manage"]}
    http_method_names = ["get", "post", "delete"]
    pagination_class = None

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return self.base_queryset().filter(accepted_at__isnull=True).order_by("-created_at")

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        inv, token = services.create_invitation(
            self.business,
            s.validated_data["role"],
            request.user,
            email=s.validated_data.get("email", ""),
            phone=s.validated_data.get("phone", ""),
        )
        inv._token = token  # type: ignore[attr-defined]
        audit(request, "invitation.create", self.business, inv)
        return Response(self.get_serializer(inv).data, status=status.HTTP_201_CREATED)
