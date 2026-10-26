from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from accounts.services import anonymize_user

User = get_user_model()


class Command(BaseCommand):
    help = "Anonimiza uma conta (LGPD): remove os dados pessoais e encerra o acesso, preservando os pedidos."

    def add_arguments(self, parser):
        parser.add_argument("email", help="E-mail da conta a anonimizar")

    def handle(self, *args, **options):
        try:
            user = User.objects.get(email__iexact=options["email"].strip())
        except User.DoesNotExist:
            raise CommandError("Usuário não encontrado.") from None
        try:
            anonymize_user(user)
        except ValueError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(self.style.SUCCESS("Conta anonimizada."))
