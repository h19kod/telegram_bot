from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import SimpleRouter

from apps.analytics import api as analytics
from apps.businesses import api as businesses
from apps.categories.api import CategoryViewSet
from apps.chatbot import api as chatbot
from apps.customers.api import CustomerViewSet
from apps.delivery.api import DeliveryZoneViewSet
from apps.orders.api import CouponViewSet, OrderViewSet, ReviewViewSet
from apps.platform_admin import api as platform
from apps.products.api import OptionGroupViewSet, OptionViewSet, ProductViewSet
from apps.staff import api as staff
from apps.subscriptions.api import SubscriptionView
from core.health import healthz, readyz


class Router(SimpleRouter):
    def __init__(self) -> None:
        super().__init__(trailing_slash="")


tenant = Router()
tenant.register("branches", businesses.BranchViewSet, basename="branch")
tenant.register("categories", CategoryViewSet, basename="category")
tenant.register("products", ProductViewSet, basename="product")
tenant.register("option-groups", OptionGroupViewSet, basename="option-group")
tenant.register("options", OptionViewSet, basename="option")
tenant.register("orders", OrderViewSet, basename="order")
tenant.register("coupons", CouponViewSet, basename="coupon")
tenant.register("reviews", ReviewViewSet, basename="review")
tenant.register("customers", CustomerViewSet, basename="customer")
tenant.register("delivery-zones", DeliveryZoneViewSet, basename="delivery-zone")
tenant.register("roles", staff.RoleViewSet, basename="role")
tenant.register("members", staff.MemberViewSet, basename="member")
tenant.register("invitations", staff.InvitationViewSet, basename="invitation")
tenant.register("support-tickets", platform.BusinessSupportViewSet, basename="b-ticket")
tenant.register("knowledge", chatbot.KnowledgeViewSet, basename="knowledge")
tenant.register("ai/conversations", chatbot.ConversationViewSet, basename="ai-conversation")

tenant_urls = [
    path("", businesses.BusinessView.as_view()),
    path("images/<str:kind>", businesses.BusinessImageView.as_view()),
    path("settings", businesses.SettingsView.as_view()),
    path("telegram", businesses.TelegramView.as_view()),
    path("telegram/test-notification", businesses.TelegramTestView.as_view()),
    path("qr", businesses.QRCodeView.as_view()),
    path("permissions", staff.PermissionListView.as_view()),
    path("analytics/overview", analytics.OverviewView.as_view()),
    path("analytics/sales", analytics.SalesView.as_view()),
    path("analytics/top-products", analytics.TopProductsView.as_view()),
    path("analytics/recent-customers", analytics.RecentCustomersView.as_view()),
    path("subscription", SubscriptionView.as_view()),
    path("audit-log", platform.BusinessAuditView.as_view()),
    *tenant.urls,
]

platform_router = Router()
platform_router.register("businesses", platform.PlatformBusinessViewSet, basename="p-business")
platform_router.register("features", platform.FeatureViewSet, basename="p-feature")
platform_router.register("plans", platform.PlanViewSet, basename="p-plan")
platform_router.register("support-tickets", platform.PlatformSupportViewSet, basename="p-ticket")

platform_urls = [
    path("stats", platform.PlatformStatsView.as_view()),
    path("health", platform.PlatformHealthView.as_view()),
    path("audit-log", platform.PlatformAuditView.as_view()),
    path(
        "subscriptions/<uuid:subscription_id>/payments", platform.SubscriptionPaymentView.as_view()
    ),
    *platform_router.urls,
]

api_v1 = [
    path("auth/", include("apps.accounts.urls")),
    path("businesses", businesses.MyBusinessesView.as_view()),
    path("governorates", businesses.GovernorateListView.as_view()),
    path("b/<uuid:business_id>/", include(tenant_urls)),
    path("store/<slug:slug>/", include("apps.storefront.urls")),
    path("platform/", include(platform_urls)),
]

urlpatterns = [
    path("healthz", healthz),
    path("readyz", readyz),
    path("api/v1/", include(api_v1)),
    path("internal/v1/", include("apps.internal_api.urls")),
    path("django-admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema")),
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
