from decimal import Decimal

from rest_framework import serializers

from products.models import Product

from .models import Cart, CartItem


class CartProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["slug", "name", "price", "stock"]


class CartItemSerializer(serializers.ModelSerializer):
    product = CartProductSerializer(read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    available = serializers.BooleanField(read_only=True)

    class Meta:
        model = CartItem
        fields = ["product", "quantity", "subtotal", "available"]


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    items_count = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ["id", "items", "items_count", "total"]

    def get_items_count(self, cart):
        return sum(item.quantity for item in cart.items.all())

    def get_total(self, cart):
        # só conta o que está disponível (produto ativo e com estoque)
        total = sum((i.subtotal for i in cart.items.all() if i.available), Decimal("0.00"))
        return f"{total:.2f}"


class AddItemSerializer(serializers.Serializer):
    product = serializers.SlugField()
    quantity = serializers.IntegerField(min_value=1, default=1)


class QuantitySerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)
