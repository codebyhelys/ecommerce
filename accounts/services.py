from django.apps import apps
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from knox.models import AuthToken
from rest_framework.exceptions import ValidationError

from .emails import send_password_reset_email
from .models import Address

User = get_user_model()


@transaction.atomic
def anonymize_user(user):
    """Remove os dados pessoais da conta e encerra o acesso, preservando o histórico de pedidos.

    Os pedidos continuam ligados ao usuário (obrigação fiscal), com o endereço de entrega que foi copiado
    para eles na compra. O e-mail original fica livre para um novo cadastro.
    """
    user = User.objects.select_for_update().get(pk=user.pk)
    if user.is_staff or user.is_superuser:
        raise ValueError("Contas de equipe não podem ser anonimizadas por aqui.")

    user.email = f"anonimo-{user.pk}@anonimo.invalid"
    user.first_name = ""
    user.last_name = ""
    user.is_active = False
    user.set_unusable_password()
    user.save()

    AuthToken.objects.filter(user=user).delete()
    Address.objects.filter(user=user).delete()
    apps.get_model("cart", "Cart").objects.filter(user=user).delete()  # sem importar o app cart
    apps.get_model("reviews", "Review").objects.filter(user=user).delete()  # texto livre pode conter dados pessoais
    return user


@transaction.atomic
def create_address(user, data):
    User.objects.select_for_update().get(pk=user.pk)  # serializa as criações do mesmo usuário
    if user.addresses.count() >= Address.MAX_PER_USER:
        raise ValidationError({"detail": f"Limite de {Address.MAX_PER_USER} endereços por conta."})
    make_default = bool(data.get("is_default")) or not user.addresses.exists()
    if make_default:
        user.addresses.filter(is_default=True).update(is_default=False)
    return Address.objects.create(user=user, **{**data, "is_default": make_default})


@transaction.atomic
def update_address(address, data):
    User.objects.select_for_update().get(pk=address.user_id)
    address = Address.objects.get(pk=address.pk)
    data = dict(data)
    if data.get("is_default") is False and address.is_default:
        data.pop("is_default")  # para trocar o padrão, marque OUTRO endereço como padrão
    if data.get("is_default"):
        Address.objects.filter(user_id=address.user_id, is_default=True).exclude(pk=address.pk).update(is_default=False)
    for attr, value in data.items():
        setattr(address, attr, value)
    address.save()
    return address


@transaction.atomic
def delete_address(address):
    user_id, was_default = address.user_id, address.is_default
    User.objects.select_for_update().get(pk=user_id)
    address.delete()
    if was_default:  # promove o mais recente, para sempre haver um padrão
        newest = Address.objects.filter(user_id=user_id).order_by("-created_at", "-id").first()
        if newest:
            newest.is_default = True
            newest.save(update_fields=["is_default", "updated_at"])


def request_password_reset(email):
    """Envia o link de redefinição se a conta existir. Quem chama responde sempre o mesmo (não revela contas)."""
    user = User.objects.filter(email__iexact=email.strip(), is_active=True).first()
    if user is not None and user.has_usable_password():
        send_password_reset_email(user)


def _validate_new_password(user, new_password):
    try:
        password_validation.validate_password(new_password, user)
    except DjangoValidationError as exc:
        raise ValidationError({"new_password": list(exc.messages)}) from None


@transaction.atomic
def reset_password(uid, token, new_password):
    try:
        user = User.objects.select_for_update().get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    if user is None or not default_token_generator.check_token(user, token):
        raise ValidationError({"token": "Link inválido ou expirado."})
    _validate_new_password(user, new_password)
    user.set_password(new_password)  # o token deixa de valer sozinho: ele depende do hash da senha
    user.save(update_fields=["password"])
    AuthToken.objects.filter(user=user).delete()  # encerra todas as sessões abertas
    return user


@transaction.atomic
def change_password(user, new_password, keep_token=None):
    _validate_new_password(user, new_password)
    user.set_password(new_password)
    user.save(update_fields=["password"])
    others = AuthToken.objects.filter(user=user)
    if keep_token is not None:
        others = others.exclude(pk=keep_token.pk)
    others.delete()  # quem estava logado em outro lugar precisa entrar de novo
