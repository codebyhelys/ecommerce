from rest_framework import serializers

from . import services
from .models import Order, OrderItem

SHIPPING_FIELDS = [
    "shipping_name",
    "shipping_zip_code",
    "shipping_street",
    "shipping_number",
    "shipping_complement",
    "shipping_district",
    "shipping_city",
    "shipping_state",
]


class OrderItemSerializer(serializers.ModelSerializer):
    product = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ["product", "product_name", "unit_price", "quantity", "subtotal"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ["id", "status", "total", "items", *SHIPPING_FIELDS, "created_at"]
        read_only_fields = fields


class OrderCreateSerializer(serializers.ModelSerializer):
    """Recebe só o endereço de entrega; os itens vêm do carrinho do usuário."""

    class Meta:
        model = Order
        fields = SHIPPING_FIELDS

    def validate_shipping_state(self, value):
        value = value.strip().upper()
        if len(value) != 2 or not value.isalpha():
            raise serializers.ValidationError("Informe a sigla do estado com 2 letras.")
        return value

    def validate_shipping_zip_code(self, value):
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) != 8:
            raise serializers.ValidationError("CEP deve ter 8 dígitos.")
        return f"{digits[:5]}-{digits[5:]}"

    def create(self, validated_data):
        return services.create_order(user=self.context["request"].user, shipping=validated_data)

    def to_representation(self, instance):
        return OrderSerializer(instance, context=self.context).data
