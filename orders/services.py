from decimal import Decimal

from django.db import transaction
from django.db.models import F
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
        p.pk: p
        for p in Product.objects.select_for_update()
        .filter(pk__in=[i.product_id for i in items])
        .order_by("id")
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
            order=order, product=product, product_name=product.name,
            unit_price=product.price, quantity=item.quantity,
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
            stock=F("stock") + item.quantity, updated_at=timezone.now(),
        )

    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    return order
