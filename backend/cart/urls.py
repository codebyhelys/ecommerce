from django.urls import path

from .views import CartItemCreateView, CartItemDetailView, CartView

urlpatterns = [
    path("cart/", CartView.as_view(), name="cart"),
    path("cart/items/", CartItemCreateView.as_view(), name="cart-item-add"),
    path("cart/items/<slug:slug>/", CartItemDetailView.as_view(), name="cart-item-detail"),
]
