from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction
from knox.models import AuthToken

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
    apps.get_model("cart", "Cart").objects.filter(user=user).delete()  # sem importar o app cart
    return user
