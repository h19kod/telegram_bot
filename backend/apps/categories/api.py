from __future__ import annotations

from typing import Any

from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.categories.models import Category
from apps.products import services as catalog
from core.images import validate_and_process_image
from core.tenancy import TenantPrimaryKeyRelatedField, TenantViewSet


class CategorySerializer(serializers.ModelSerializer):
    parent = TenantPrimaryKeyRelatedField(
        queryset=Category.objects.all(), required=False, allow_null=True
    )
    products_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = [
            "id",
            "name_ar",
            "name_en",
            "image",
            "parent",
            "sort_order",
            "is_active",
            "products_count",
            "created_at",
        ]
        read_only_fields = ["id", "image", "created_at"]


class ReorderSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), max_length=500)


class CategoryViewSet(TenantViewSet):
    model = Category
    serializer_class = CategorySerializer
    required_permissions = {
        "list": ["catalog.view"],
        "retrieve": ["catalog.view"],
        "write": ["catalog.edit"],
    }
    pagination_class = None

    def get_queryset(self):  # type: ignore[no-untyped-def]
        from django.db.models import Count, Q

        return (
            self.base_queryset()
            .filter(is_archived=False)
            .annotate(products_count=Count("products", filter=Q(products__is_archived=False)))
        )

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        serializer.instance = catalog.create_category(self.business.id, **serializer.validated_data)

    def perform_destroy(self, instance: Category) -> None:
        instance.is_archived = True
        instance.is_active = False
        instance.save(update_fields=["is_archived", "is_active", "updated_at"])

    @action(detail=False, methods=["post"])
    def reorder(self, request: Request, business_id: Any) -> Response:
        s = ReorderSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        catalog.reorder(Category, self.business.id, s.validated_data["ids"])
        return Response(status=204)

    @action(detail=True, methods=["post"])
    def image(self, request: Request, business_id: Any, pk: Any = None) -> Response:
        category = self.get_object()
        processed = validate_and_process_image(request.FILES.get("image"), max_side=800)
        category.image = processed.image
        category.save(update_fields=["image", "updated_at"])
        return Response(CategorySerializer(category, context=self.get_serializer_context()).data)
