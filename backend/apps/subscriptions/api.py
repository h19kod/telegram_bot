from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.categories.models import Category
from apps.products.models import Product
from apps.staff.models import Membership
from apps.subscriptions import services
from apps.subscriptions.models import Plan
from core.tenancy import IsBusinessMember


def plan_data(plan: Plan) -> dict[str, Any]:
    return {
        "code": plan.code,
        "name_ar": plan.name_ar,
        "name_en": plan.name_en,
        "monthly_price": plan.monthly_price,
        "currency": plan.currency,
        "trial_days": plan.trial_days,
        "entitlements": {e.feature_id: e.value for e in plan.entitlements.all()},
    }


PLAN = inline_serializer(
    "PublicPlan",
    {
        "code": serializers.CharField(),
        "name_ar": serializers.CharField(),
        "name_en": serializers.CharField(),
        "monthly_price": serializers.IntegerField(help_text="Minor units"),
        "currency": serializers.CharField(),
        "trial_days": serializers.IntegerField(),
        "entitlements": serializers.DictField(
            child=serializers.JSONField(allow_null=True),
            help_text="feature code → value (null = unlimited)",
        ),
    },
    many=True,
)


class SubscriptionView(APIView):
    permission_classes = [IsBusinessMember]

    @extend_schema(
        tags=["subscription"],
        responses=inline_serializer(
            "SubscriptionOverview",
            {
                "subscription": inline_serializer(
                    "CurrentSubscription",
                    {
                        "plan": serializers.CharField(),
                        "status": serializers.CharField(),
                        "current_period_end": serializers.DateTimeField(allow_null=True),
                        "grace_until": serializers.DateTimeField(allow_null=True),
                    },
                    allow_null=True,
                ),
                "entitlements": serializers.DictField(
                    child=serializers.JSONField(allow_null=True),
                    help_text="feature code → resolved value (null = unlimited)",
                ),
                "usage": serializers.DictField(
                    child=serializers.IntegerField(), help_text="limit key → current usage"
                ),
                "plans": PLAN,
            },
        ),
    )
    def get(self, request: Request, business_id: Any) -> Response:
        b = request.business
        sub = services.live_subscription(b.id)
        usage = services.usage(b.id)
        usage.update(
            {
                "max_products": Product.objects.for_business(b).filter(is_archived=False).count(),
                "max_categories": Category.objects.for_business(b)
                .filter(is_archived=False)
                .count(),
                "max_staff": Membership.objects.for_business(b).filter(is_active=True).count(),
                "max_branches": b.branches.count(),
            }
        )
        return Response(
            {
                "subscription": {
                    "plan": sub.plan.code,
                    "status": sub.status,
                    "current_period_end": sub.current_period_end,
                    "grace_until": sub.grace_until,
                }
                if sub
                else None,
                "entitlements": services.resolve_all(b.id),
                "usage": usage,
                "plans": [
                    plan_data(p)
                    for p in Plan.objects.filter(is_public=True, is_active=True).prefetch_related(
                        "entitlements"
                    )
                ],
            }
        )
