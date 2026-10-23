from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Payment(models.Model):
    class Method(models.TextChoices):
        PIX = "pix", "Pix"
        CARD = "card", "Cartão"
        BOLETO = "boleto", "Boleto"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        APPROVED = "approved", "Aprovado"
        FAILED = "failed", "Recusado"
        CANCELLED = "cancelled", "Cancelado"
        REFUNDED = "refunded", "Estornado"

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="payments")
    provider = models.CharField(max_length=30)
    method = models.CharField(max_length=10, choices=Method.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    # valor congelado na criação: o webhook precisa bater com ele
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    provider_reference = models.CharField(max_length=100, blank=True)
    # só dados que o cliente pode ver (ex.: código Pix copia-e-cola, link de checkout)
    payment_data = models.JSONField(default=dict, blank=True)
    # pago depois de o pedido ter sido cancelado: alguém precisa devolver o dinheiro
    needs_refund = models.BooleanField(default=False)
    refunded_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            # no máximo UM pagamento ativo (pendente ou aprovado) por pedido: impede cobrança em duplicidade
            models.UniqueConstraint(
                fields=["order"],
                condition=models.Q(status__in=["pending", "approved"]),
                name="payment_one_active_per_order",
            ),
            models.UniqueConstraint(
                fields=["provider", "provider_reference"],
                condition=~models.Q(provider_reference=""),
                name="payment_unique_provider_reference",
            ),
        ]

    def __str__(self):
        return f"Pagamento #{self.pk} ({self.get_status_display()})"


class WebhookEvent(models.Model):
    provider = models.CharField(max_length=30)
    event_id = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "event_id"], name="webhookevent_unique_event"),
        ]

    def __str__(self):
        return f"{self.provider}:{self.event_id}"
