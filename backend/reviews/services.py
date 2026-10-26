from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.exceptions import APIException

from orders.models import Order

from .models import Review

# pedido cancelado ou ainda pendente não dá direito a avaliar
PURCHASED_STATUSES = [Order.Status.PAID, Order.Status.SHIPPED, Order.Status.DELIVERED]


class NotAPurchaser(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Só quem comprou o produto pode avaliá-lo."
    default_code = "not_a_purchaser"


class AlreadyReviewed(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Você já avaliou este produto. Edite a avaliação existente."
    default_code = "already_reviewed"


def has_purchased(user, product):
    return Order.objects.filter(user=user, status__in=PURCHASED_STATUSES, items__product=product).exists()


def create_review(*, user, product, rating, comment=""):
    if not has_purchased(user, product):
        raise NotAPurchaser()
    try:
        with transaction.atomic():  # savepoint: a unicidade (usuário, produto) é garantida pelo banco
            return Review.objects.create(product=product, user=user, rating=rating, comment=comment)
    except IntegrityError:
        raise AlreadyReviewed() from None
