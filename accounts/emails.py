from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from core.tasks import enqueue

from .models import User


def deliver_password_reset_email(user_id):
    """Monta e envia o e-mail. O token nasce aqui, na hora do envio: nunca trafega pela fila."""
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None or not user.has_usable_password():
        return
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f"{settings.FRONTEND_URL.rstrip('/')}/redefinir-senha?uid={uid}&token={token}"
    minutes = settings.PASSWORD_RESET_TIMEOUT // 60
    body = (
        "Olá!\n\n"
        "Recebemos um pedido para redefinir a senha da sua conta. Para escolher uma nova senha, acesse:\n\n"
        f"{link}\n\n"
        f"O link vale por {minutes} minutos e só pode ser usado uma vez.\n"
        "Se você não fez esse pedido, ignore este e-mail: sua senha continua a mesma."
    )
    send_mail("Redefinição de senha", body, settings.DEFAULT_FROM_EMAIL, [user.email])


def send_password_reset_email(user):
    """Envia em segundo plano: assim a resposta demora o mesmo exista a conta ou não (sem pista do cadastro)."""
    from .tasks import send_password_reset_email_task

    enqueue(send_password_reset_email_task, user.pk, inline=deliver_password_reset_email)
