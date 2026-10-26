from django.db import transaction
from django.db.models import Prefetch
from rest_framework.exceptions import NotFound, ValidationError

from products.models import Product

from .models import Cart, CartItem

MAX_PER_ITEM = 99


def get_cart(user):
    qs = Cart.objects.prefetch_related(Prefetch("items", queryset=CartItem.objects.select_related("product")))
    cart = qs.filter(user=user).first()
    if cart is None:
        Cart.objects.get_or_create(user=user)
        cart = qs.get(user=user)
    return cart


def _active_product(slug):
    try:
        return Product.objects.get(slug=slug, is_active=True)
    except Product.DoesNotExist:
        raise ValidationError({"product": "Produto não encontrado ou indisponível."}) from None


def _check_quantity(product, quantity):
    if quantity > MAX_PER_ITEM:
        raise ValidationError({"quantity": f"Máximo de {MAX_PER_ITEM} unidades por item."})
    if quantity > product.stock:
        raise ValidationError({"quantity": f"Estoque insuficiente: disponível {product.stock}."})


@transaction.atomic
def add_item(user, product, quantity):
    cart, _ = Cart.objects.get_or_create(user=user)
    product = _active_product(product)
    _check_quantity(product, quantity)

    item, created = CartItem.objects.select_for_update().get_or_create(
        cart=cart, product=product, defaults={"quantity": quantity}
    )
    if not created:
        new_quantity = item.quantity + quantity
        _check_quantity(product, new_quantity)
        item.quantity = new_quantity
        item.save(update_fields=["quantity", "updated_at"])


@transaction.atomic
def set_quantity(user, slug, quantity):
    item = (
        CartItem.objects.select_for_update()
        .select_related("product")
        .filter(cart__user=user, product__slug=slug)
        .first()
    )
    if item is None:
        raise NotFound("Item não está no carrinho.")
    if not item.product.is_active:
        raise ValidationError({"product": "Produto indisponível. Remova-o do carrinho."})
    _check_quantity(item.product, quantity)
    item.quantity = quantity
    item.save(update_fields=["quantity", "updated_at"])


def remove_item(user, slug):
    deleted, _ = CartItem.objects.filter(cart__user=user, product__slug=slug).delete()
    if not deleted:
        raise NotFound("Item não está no carrinho.")


def clear_cart(user):
    CartItem.objects.filter(cart__user=user).delete()
