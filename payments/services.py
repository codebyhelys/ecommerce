import logging

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound

from orders.models import Order

from .gateways import get_gateway
from .models import Payment, WebhookEvent

logger = logging.getLogger(__name__)

# transições aceitas pelo webhook: estado atual -> estados de destino
ALLOWED_TRANSITIONS = {
    Payment.Status.PENDING: {Payment.Status.APPROVED, Payment.Status.FAILED, Payment.Status.CANCELLED},
    # cliente pagou o Pix depois de o pedido ser cancelado: registramos para estornar
    Payment.Status.CANCELLED: {Payment.Status.APPROVED},
}


class PaymentConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Não é possível iniciar o pagamento deste pedido."
    default_code = "payment_conflict"


class GatewayUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Provedor de pagamento indisponível. Tente novamente."
    default_code = "gateway_unavailable"


def start_payment(*, user, order_id, method):
    gateway = get_gateway()

    # 1) valida e reserva a vaga de pagamento (rápido, com trava no pedido)
    with transaction.atomic():
        order = Order.objects.select_for_update().filter(pk=order_id, user=user).first()
        if order is None:
            raise NotFound("Pedido não encontrado.")
        if order.status != Order.Status.PENDING:
            raise PaymentConflict("O pedido não está aguardando pagamento.")
        if order.payments.filter(status__in=[Payment.Status.PENDING, Payment.Status.APPROVED]).exists():
            raise PaymentConflict("Já existe um pagamento em andamento para este pedido.")
        payment = Payment.objects.create(
            order=order, provider=gateway.name, method=method, amount=order.total,
        )

    # 2) chama o provedor FORA da transação: rede lenta não segura trava no banco
    try:
        result = gateway.create_payment(payment)
    except Exception:
        logger.exception("Falha ao criar pagamento %s no provedor %s", payment.pk, gateway.name)
        Payment.objects.filter(pk=payment.pk).update(
            status=Payment.Status.FAILED, updated_at=timezone.now()
        )  # libera a vaga para uma nova tentativa
        raise GatewayUnavailable()

    payment.provider_reference = result.reference
    payment.payment_data = result.data
    payment.save(update_fields=["provider_reference", "payment_data", "updated_at"])
    return payment


def handle_webhook(provider, headers, body):
    """Devolve 'processed', 'duplicate' ou 'ignored'. Levanta InvalidWebhook / UnknownGateway."""
    gateway = get_gateway(provider)
    event = gateway.parse_webhook(headers, body)  # verifica a assinatura ANTES de tudo

    with transaction.atomic():
        try:
            with transaction.atomic():  # savepoint: só este insert vira "duplicado"
                WebhookEvent.objects.create(provider=gateway.name, event_id=event.event_id, payload=event.raw)
        except IntegrityError:
            return "duplicate"
        return _apply_event(gateway.name, event)


def _apply_event(provider, event):
    payment = (
        Payment.objects.select_for_update()
        .filter(provider=provider, provider_reference=event.reference)
        .first()
    )
    if payment is None:
        logger.warning("Webhook %s para referência desconhecida %s", event.event_id, event.reference)
        return "ignored"

    if event.amount is not None and event.amount != payment.amount:
        logger.warning("Webhook %s com valor divergente (%s != %s)", event.event_id, event.amount, payment.amount)
        return "ignored"

    new_status = Payment.Status(event.status)
    if new_status not in ALLOWED_TRANSITIONS.get(payment.status, set()):
        return "ignored"  # repetido, fora de ordem ou sem efeito

    order = Order.objects.select_for_update().get(pk=payment.order_id)
    payment.status = new_status
    if new_status == Payment.Status.APPROVED:
        payment.paid_at = timezone.now()
        if order.status == Order.Status.PENDING:
            order.status = Order.Status.PAID
            order.save(update_fields=["status", "updated_at"])
        else:
            payment.needs_refund = True
            logger.error("Pagamento %s aprovado para pedido %s em estado %s: estornar", payment.pk, order.pk, order.status)
    payment.save()
    return "processed"