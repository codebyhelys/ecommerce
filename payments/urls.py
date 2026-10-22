from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import PaymentViewSet, WebhookView

router = SimpleRouter()
router.register("payments", PaymentViewSet, basename="payment")

urlpatterns = [
    path("payments/webhooks/<str:provider>/", WebhookView.as_view(), name="payment-webhook"),
    *router.urls,
]