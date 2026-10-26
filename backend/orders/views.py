from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from . import services
from .models import Order, OrderItem
from .serializers import OrderCreateSerializer, OrderSerializer


class OrderViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # geração do esquema OpenAPI, sem usuário
            return Order.objects.none()
        items = OrderItem.objects.select_related("product")
        qs = Order.objects.prefetch_related(Prefetch("items", queryset=items))
        if not self.request.user.is_staff:
            qs = qs.filter(user=self.request.user)
        return qs

    def get_serializer_class(self):
        return OrderCreateSerializer if self.action == "create" else OrderSerializer

    @extend_schema(request=None, responses=OrderSerializer)
    @action(detail=True, methods=["POST"])
    def cancel(self, request, pk=None):
        order = services.cancel_order(self.get_object())
        return Response(OrderSerializer(order, context=self.get_serializer_context()).data)
