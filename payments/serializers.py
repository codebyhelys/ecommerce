from rest_framework import serializers

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "order", "method", "status", "amount", "payment_data", "created_at", "paid_at"]

        read_only_fields = fields


class PaymentCreateSerializer(serializers.Serializer):
    """O cliente escolhe só o pedido e o método; valor e status são do servidor."""

    order = serializers.IntegerField(min_value=1)
    method = serializers.ChoiceField(choices=Payment.Method.choices)
