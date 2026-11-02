from django.urls import path

from apps.storefront import views as v

urlpatterns = [
    path("session", v.SessionView.as_view()),
    path("", v.InfoView.as_view()),
    path("categories", v.CategoriesView.as_view()),
    path("products", v.ProductsView.as_view()),
    path("products/<uuid:product_id>", v.ProductDetailView.as_view()),
    path("delivery-zones", v.ZonesView.as_view()),
    path("cart", v.CartView.as_view()),
    path("cart/items", v.CartItemsView.as_view()),
    path("cart/items/<uuid:item_id>", v.CartItemView.as_view()),
    path("checkout/quote", v.QuoteView.as_view()),
    path("checkout", v.CheckoutView.as_view()),
    path("orders", v.OrdersView.as_view()),
    path("orders/<uuid:order_id>", v.OrderDetailView.as_view()),
    path("orders/<uuid:order_id>/cancel", v.OrderCancelView.as_view()),
    path("me", v.MeView.as_view()),
    path("me/phone/code", v.PhoneCodeView.as_view()),
    path("me/phone/confirm", v.PhoneConfirmView.as_view()),
    path("me/addresses", v.AddressesView.as_view()),
    path("me/addresses/<uuid:address_id>", v.AddressDetailView.as_view()),
    path("support", v.SupportView.as_view()),
]
