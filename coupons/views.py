from decimal import Decimal

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import permissions, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from cart import services as cart_services
from orders.shipping import calculate_shipping

from . import services
from .serializers import CouponCodeSerializer


class CouponValidateView(APIView):
    """Pré-visualiza o cupom sobre o carrinho atual, sem usá-lo.

    Limitado por escopo (`coupon`) para impedir a tentativa de adivinhar códigos.
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "coupon"

    @extend_schema(
        request=CouponCodeSerializer,
        responses=inline_serializer(
            "CouponPreview",
            {
                name: serializers.CharField()
                for name in ("code", "description", "subtotal", "discount", "shipping_cost", "total")
            },
        ),
    )
    def post(self, request):
        serializer = CouponCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart = cart_services.get_cart(request.user)
        subtotal = sum((i.subtotal for i in cart.items.all() if i.available), Decimal("0.00"))
        if subtotal <= 0:
            raise ValidationError({"cart": "Carrinho vazio."})

        coupon, discount = services.get_valid_coupon(
            serializer.validated_data["code"], user=request.user, subtotal=subtotal
        )
        shipping_cost = calculate_shipping(subtotal - discount)
        return Response(
            {
                "code": coupon.code,
                "description": coupon.description,
                "subtotal": f"{subtotal:.2f}",
                "discount": f"{discount:.2f}",
                "shipping_cost": f"{shipping_cost:.2f}",
                "total": f"{subtotal - discount + shipping_cost:.2f}",
            }
        )
