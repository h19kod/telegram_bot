from __future__ import annotations

from rest_framework import serializers

from apps.accounts.models import User
from apps.staff.models import Membership


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=32)
    password = serializers.CharField(write_only=True, min_length=10, max_length=128)
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    language = serializers.ChoiceField(choices=["ar", "en"], default="ar")


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)
    password = serializers.CharField(max_length=128, write_only=True)
    otp = serializers.CharField(max_length=10, required=False, allow_blank=True)


class UserSerializer(serializers.ModelSerializer):
    has_telegram = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "phone",
            "full_name",
            "language",
            "is_platform_admin",
            "totp_enabled",
            "has_telegram",
            "date_joined",
        ]
        read_only_fields = [
            "id",
            "email",
            "phone",
            "is_platform_admin",
            "totp_enabled",
            "date_joined",
        ]

    def get_has_telegram(self, obj: User) -> bool:
        return hasattr(obj, "telegram")


class MembershipSerializer(serializers.ModelSerializer):
    business_id = serializers.UUIDField(source="business.id")
    business_slug = serializers.CharField(source="business.slug")
    business_name_ar = serializers.CharField(source="business.name_ar")
    business_name_en = serializers.CharField(source="business.name_en")
    business_status = serializers.CharField(source="business.status")
    role = serializers.CharField(source="role.name")
    is_owner = serializers.BooleanField(source="role.is_owner")
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = [
            "id",
            "business_id",
            "business_slug",
            "business_name_ar",
            "business_name_en",
            "business_status",
            "role",
            "is_owner",
            "permissions",
        ]

    def get_permissions(self, obj: Membership) -> list[str]:
        return sorted(obj.permission_set())


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(max_length=128)
    new_password = serializers.CharField(min_length=10, max_length=128)


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=10, max_length=128)


class OtpSerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=10)
