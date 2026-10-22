from datetime import timedelta
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.db.models import Exists, F, OuterRef
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError

from cart.models import Cart
from cart.services import clear_cart
from products.models import Product

from .models import Order, OrderItem


class InvalidOrderState(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "O pedido não está em um estado que permita esta ação."
    default_code = "invalid_order_state"


@transaction.atomic
def create_order(*, user, shipping):
    # trava o carrinho: duas finalizações simultâneas não geram pedido duplicado
    cart = Cart.objects.select_for_update().filter(user=user).first()
    items = list(cart.items.select_related("product").order_by("product_id")) if cart else []
    if not items:
        raise ValidationError({"cart": "Carrinho vazio."})

    # trava os produtos (sempre em ordem de id, evitando deadlock) e relê o estoque atual
    products = {
        p.pk: p for p in Product.objects.select_for_update().filter(pk__in=[i.product_id for i in items]).order_by("id")
    }

    errors = []
    for item in items:
        product = products[item.product_id]
        if not product.is_active:
            errors.append(f"'{product.slug}' não está mais disponível.")
        elif product.stock < item.quantity:
            errors.append(
                f"Estoque insuficiente para '{product.slug}': disponível {product.stock}, no carrinho {item.quantity}."
            )
    if errors:
        raise ValidationError({"items": errors})

    order = Order.objects.create(user=user, **shipping)
    total = Decimal("0.00")
    for item in items:
        product = products[item.product_id]
        OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            unit_price=product.price,
            quantity=item.quantity,
        )
        product.stock -= item.quantity
        product.save(update_fields=["stock", "updated_at"])
        total += product.price * item.quantity

    order.total = total
    order.save(update_fields=["total", "updated_at"])
    clear_cart(user)
    return order


@transaction.atomic
def cancel_order(order):
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status != Order.Status.PENDING:
        raise InvalidOrderState("Só é possível cancelar pedidos pendentes.")

    for item in order.items.all():
        Product.objects.filter(pk=item.product_id).update(
            stock=F("stock") + item.quantity,
            updated_at=timezone.now(),
        )

    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    # um pagamento ainda pendente deste pedido deixa de valer
    order.payments.filter(status="pending").update(status="cancelled", updated_at=timezone.now())
    return order


def _advance(order, expected, new):
    """Move o pedido de `expected` para `new`; qualquer outro estado de origem é recusado."""
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status != expected:
            raise InvalidOrderState(
                f"Pedido #{order.pk}: precisa estar '{expected.label}' (está '{order.get_status_display()}')."
            )
        order.status = new
        order.save(update_fields=["status", "updated_at"])
        return order


def ship_order(order):
    return _advance(order, Order.Status.PAID, Order.Status.SHIPPED)


def deliver_order(order):
    return _advance(order, Order.Status.SHIPPED, Order.Status.DELIVERED)


def expire_pending_orders():
    """Cancela pedidos pendentes antigos (devolvendo o estoque) e libera pagamentos presos.

    Devolve (pedidos_expirados, pagamentos_liberados). Seguro para rodar de tempos em tempos:
    cada cancelamento relê o pedido com trava e ignora o que já foi pago ou cancelado.
    """
    Payment = apps.get_model("payments", "Payment")  # sem importar o app payments (evita acoplamento)
    now = timezone.now()
    order_cutoff = now - timedelta(minutes=settings.ORDER_PENDING_TTL_MINUTES)
    window_cutoff = now - timedelta(minutes=settings.PAYMENT_WINDOW_MINUTES)
    stale_cutoff = now - timedelta(minutes=settings.PAYMENT_STALE_MINUTES)

    # 1) pagamento criado mas nunca enviado ao provedor (ex.: servidor caiu no meio): libera a vaga do pedido
    stuck = Payment.objects.filter(status="pending", provider_reference="", created_at__lt=stale_cutoff).update(
        status="failed", updated_at=now
    )

    # 2) pedido pendente antigo e SEM pagamento em andamento dentro da janela (ex.: Pix ainda válido)
    paying = Payment.objects.filter(order=OuterRef("pk"), status="pending", created_at__gte=window_cutoff)
    expired = 0
    stale_orders = (
        Order.objects.filter(status=Order.Status.PENDING, created_at__lt=order_cutoff)
        .annotate(has_open_payment=Exists(paying))
        .filter(has_open_payment=False)
        .values_list("pk", flat=True)
    )
    for pk in list(stale_orders):
        try:
            cancel_order(Order(pk=pk))
            expired += 1
        except InvalidOrderState:
            continue  # foi paga ou cancelada enquanto isso
    return expired, stuck
