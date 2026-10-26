from rest_framework import serializers

from accounts.models import Address
from core.br import normalize_state, normalize_zip_code

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
REQUIRED_SHIPPING_FIELDS = [f for f in SHIPPING_FIELDS if f != "shipping_complement"]


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
        fields = [
            "id",
            "status",
            "subtotal",
            "discount",
            "shipping_cost",
            "total",
            "coupon_code",
            "tracking_code",
            "items",
            *SHIPPING_FIELDS,
            "created_at",
        ]
        read_only_fields = fields


class OrderCreateSerializer(serializers.ModelSerializer):
    """Recebe o endereço de entrega (um endereço salvo OU os campos); os itens vêm do carrinho."""

    address = serializers.PrimaryKeyRelatedField(
        queryset=Address.objects.all(),
        required=False,
        write_only=True,
        error_messages={"does_not_exist": "Endereço inválido."},
    )
    coupon = serializers.CharField(required=False, allow_blank=True, write_only=True, max_length=40)

    class Meta:
        model = Order
        fields = [*SHIPPING_FIELDS, "address", "coupon"]
        extra_kwargs = {field: {"required": False} for field in SHIPPING_FIELDS}

    def validate_address(self, value):
        if value.user_id != self.context["request"].user.pk:
            raise serializers.ValidationError("Endereço inválido.")  # mesma mensagem de "não existe"
        return value

    def validate_shipping_state(self, value):
        try:
            return normalize_state(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from None

    def validate_shipping_zip_code(self, value):
        try:
            return normalize_zip_code(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from None

    def validate(self, attrs):
        address = attrs.pop("address", None)
        if address is not None:  # o endereço salvo prevalece sobre campos avulsos
            attrs.update(
                shipping_name=address.recipient_name,
                shipping_zip_code=address.zip_code,
                shipping_street=address.street,
                shipping_number=address.number,
                shipping_complement=address.complement,
                shipping_district=address.district,
                shipping_city=address.city,
                shipping_state=address.state,
            )
        missing = {f: ["Este campo é obrigatório."] for f in REQUIRED_SHIPPING_FIELDS if not attrs.get(f)}
        if missing:
            raise serializers.ValidationError(missing)
        return attrs

    def create(self, validated_data):
        coupon_code = validated_data.pop("coupon", "")
        return services.create_order(
            user=self.context["request"].user, shipping=validated_data, coupon_code=coupon_code
        )

    def to_representation(self, instance):
        return OrderSerializer(instance, context=self.context).data
