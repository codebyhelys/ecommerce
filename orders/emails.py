import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

SUBJECTS = {
    "created": "Recebemos o seu pedido #{id}",
    "paid": "Pagamento confirmado: pedido #{id}",
    "shipped": "Seu pedido #{id} foi enviado",
    "delivered": "Seu pedido #{id} foi entregue",
    "cancelled": "Pedido #{id} cancelado",
}

INTROS = {
    "created": "Recebemos o seu pedido. Assim que o pagamento for confirmado, avisaremos você.",
    "paid": "Recebemos o pagamento do seu pedido. Já estamos preparando o envio.",
    "shipped": "Seu pedido saiu para entrega.",
    "delivered": "Seu pedido foi entregue. Esperamos que goste!",
    "cancelled": "O seu pedido foi cancelado e os itens voltaram ao estoque. Se você já pagou, o valor será estornado.",
}


def _money(value):
    return f"R$ {value:.2f}".replace(".", ",")


def build_order_email(order, event):
    lines = [f"Olá, {order.shipping_name}!", "", INTROS[event], "", f"Pedido #{order.pk}"]
    for item in order.items.all():
        lines.append(f"  {item.quantity} x {item.product_name} ... {_money(item.unit_price * item.quantity)}")
    lines.append(f"Subtotal: {_money(order.subtotal)}")
    if order.discount:
        lines.append(f"Desconto{f' ({order.coupon_code})' if order.coupon_code else ''}: -{_money(order.discount)}")
    lines.append(f"Frete: {_money(order.shipping_cost)}")
    lines.append(f"Total: {_money(order.total)}")
    if event == "shipped" and order.tracking_code:
        lines += ["", f"Código de rastreio: {order.tracking_code}"]
    if event in ("created", "shipped"):
        lines += [
            "",
            "Entrega em:",
            f"{order.shipping_street}, {order.shipping_number} {order.shipping_complement}".strip(),
            f"{order.shipping_district} - {order.shipping_city}/{order.shipping_state} - CEP {order.shipping_zip_code}",
        ]
    return SUBJECTS[event].format(id=order.pk), "\n".join(lines)


def send_order_email(order, event):
    """Avisa o cliente. Nunca derruba quem chamou: o e-mail é consequência do pedido, não parte dele."""
    try:
        user = order.user
        if not user.is_active:  # conta encerrada/anonimizada
            return
        subject, body = build_order_email(order, event)
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])
    except Exception:
        logger.exception("Falha ao enviar o e-mail '%s' do pedido %s", event, getattr(order, "pk", "?"))
