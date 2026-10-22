import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

VALID_STATUSES = {"approved", "failed", "cancelled", "pending"}


class InvalidWebhook(Exception):
    """Assinatura inválida ou corpo mal formado."""


class UnknownGateway(Exception):
    pass


@dataclass
class GatewayResult:
    reference: str
    data: dict = field(default_factory=dict)


@dataclass
class GatewayEvent:
    event_id: str
    reference: str
    status: str
    amount: Decimal | None = None
    # id do nosso Payment, quando o provedor o devolve (ex.: external_reference no Mercado Pago)
    payment_id: int | None = None
    raw: dict = field(default_factory=dict)


class FakeGateway:
    """Provedor de mentira para desenvolvimento e testes. NÃO use em produção."""

    name = "fake"
    signature_header = "X-Signature"

    def create_payment(self, payment):
        reference = f"fake_{uuid.uuid4().hex}"
        data = {"pix_copy_paste": f"FAKE-PIX-{reference}"} if payment.method == "pix" else {}
        return GatewayResult(reference=reference, data=data)

    def parse_webhook(self, headers, body):
        secret = settings.PAYMENT_WEBHOOK_SECRET
        if not secret:
            raise InvalidWebhook("segredo do webhook não configurado")  # falha fechada

        received = headers.get(self.signature_header, "")
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(received, expected):  # comparação em tempo constante
            raise InvalidWebhook("assinatura inválida")

        try:
            payload = json.loads(body)
            amount = payload.get("amount")
            payment_id = payload.get("payment_id")
            event = GatewayEvent(
                event_id=str(payload["event_id"]),
                reference=str(payload["reference"]),
                status=str(payload["status"]),
                amount=Decimal(str(amount)) if amount is not None else None,
                payment_id=int(payment_id) if payment_id is not None else None,
                raw=payload,
            )
        except (ValueError, KeyError, TypeError, AttributeError, InvalidOperation):
            raise InvalidWebhook("payload inválido") from None
        if event.status not in VALID_STATUSES:
            raise InvalidWebhook("status desconhecido")
        return event


GATEWAYS = {"fake": FakeGateway}


def get_gateway(name=None):
    if name is None:
        name = settings.PAYMENT_GATEWAY
        if name not in GATEWAYS:
            raise ImproperlyConfigured(
                f"PAYMENT_GATEWAY inválido ou não definido: {name!r}. Opções: {', '.join(GATEWAYS)}."
            )
    try:
        return GATEWAYS[name]()
    except KeyError:
        raise UnknownGateway(name) from None
