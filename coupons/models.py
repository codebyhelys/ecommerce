from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Coupon(models.Model):
    class Kind(models.TextChoices):
        PERCENT = "percent", "Percentual"
        FIXED = "fixed", "Valor fixo"

    code = models.CharField(max_length=40, unique=True)  # sempre guardado em MAIÚSCULAS
    description = models.CharField(max_length=200, blank=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    value = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    max_discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  # teto do desconto
    min_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    starts_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)  # total de usos; vazio = ilimitado
    per_user_limit = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind="fixed") | models.Q(value__lte=100), name="coupon_percent_at_most_100"
            ),
        ]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def discount_for(self, subtotal):
        """Desconto sobre o valor dos itens. Nunca zera o pedido: sempre sobra pelo menos R$ 0,01 a pagar."""
        subtotal = Decimal(subtotal)
        if self.kind == self.Kind.PERCENT:
            amount = (subtotal * self.value / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            amount = self.value
        if self.max_discount is not None:
            amount = min(amount, self.max_discount)
        return min(amount, max(subtotal - Decimal("0.01"), Decimal("0.00")))


class CouponRedemption(models.Model):
    """Um uso do cupom, ligado ao pedido. Cancelar o pedido apaga o registro e devolve o uso."""

    coupon = models.ForeignKey(Coupon, on_delete=models.PROTECT, related_name="redemptions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="coupon_redemptions")
    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="coupon_redemption")
    discount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.coupon.code} no pedido #{self.order_id}"
