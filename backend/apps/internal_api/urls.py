from django.urls import path

from apps.internal_api import views as v

c = "bots/<uuid:bot_id>/customers/<int:tg_id>/"
urlpatterns = [
    path("bots", v.BotsView.as_view()),
    path("bots/<uuid:bot_id>/credentials", v.BotCredentialsView.as_view()),
    path("bots/<uuid:bot_id>/session", v.SessionView.as_view()),
    path("bots/<uuid:bot_id>/catalog/categories", v.CategoriesView.as_view()),
    path("bots/<uuid:bot_id>/catalog/products", v.ProductsView.as_view()),
    path("bots/<uuid:bot_id>/catalog/products/<uuid:product_id>", v.ProductDetailView.as_view()),
    path("bots/<uuid:bot_id>/zones", v.ZonesView.as_view()),
    path(c + "cart", v.CartView.as_view()),
    path(c + "cart/items", v.CartItemsView.as_view()),
    path(c + "cart/items/<uuid:item_id>", v.CartItemView.as_view()),
    path(c + "checkout/quote", v.QuoteView.as_view()),
    path(c + "checkout", v.CheckoutView.as_view()),
    path(c + "orders", v.OrdersView.as_view()),
    path(c + "orders/<uuid:order_id>", v.OrderDetailView.as_view()),
    path(c + "orders/<uuid:order_id>/cancel", v.OrderCancelView.as_view()),
    path(c + "orders/<uuid:order_id>/review", v.OrderReviewView.as_view()),
    path(c + "me", v.CustomerMeView.as_view()),
    path(c + "phone/code", v.PhoneCodeView.as_view()),
    path(c + "phone/confirm", v.PhoneConfirmView.as_view()),
    path(c + "phone/contact", v.PhoneContactView.as_view()),
    path(c + "support", v.SupportView.as_view()),
    path(c + "ai/message", v.AIMessageView.as_view()),
    path(c + "ai/proposals/<uuid:proposal_id>/confirm", v.AIConfirmView.as_view()),
    path("bots/<uuid:bot_id>/staff/transition", v.StaffTransitionView.as_view()),
    path("bots/<uuid:bot_id>/staff/link", v.StaffLinkView.as_view()),
]
