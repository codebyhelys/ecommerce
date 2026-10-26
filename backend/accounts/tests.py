import re
from datetime import timedelta
from io import StringIO

from django.apps import apps
from django.contrib.auth import authenticate, get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from knox.models import AuthToken
from rest_framework.test import APITestCase

from accounts.models import Address
from accounts.services import anonymize_user

User = get_user_model()
PASSWORD = "senha-forte-123"
SHIPPING = {
    "shipping_name": "Ana Silva",
    "shipping_zip_code": "01310-100",
    "shipping_street": "Avenida Paulista",
    "shipping_number": "1000",
    "shipping_complement": "",
    "shipping_district": "Bela Vista",
    "shipping_city": "São Paulo",
    "shipping_state": "SP",
}


class UserModelTest(TestCase):
    def test_create_user_normalizes_email(self):
        user = User.objects.create_user("Ana@Example.COM", password=PASSWORD)
        self.assertEqual(user.email, "ana@example.com")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertFalse(user.is_staff)

    def test_email_is_required(self):
        with self.assertRaises(ValueError):
            User.objects.create_user("", password=PASSWORD)

    def test_email_is_unique_ignoring_case(self):
        User.objects.create_user("ana@example.com", password=PASSWORD)
        with self.assertRaises(IntegrityError), transaction.atomic():
            User(email="ANA@example.com").save()

    def test_create_superuser_sets_flags(self):
        admin = User.objects.create_superuser("root@example.com", password=PASSWORD)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)


class UserAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("root@example.com", password=PASSWORD)
        self.client.force_login(self.admin)

    def test_changelist_loads(self):
        response = self.client.get(reverse("admin:accounts_user_changelist"))
        self.assertEqual(response.status_code, 200)

    def test_add_page_loads(self):
        response = self.client.get(reverse("admin:accounts_user_add"))
        self.assertEqual(response.status_code, 200)

    def test_admin_can_create_user(self):
        data = {"email": "nova@example.com", "password1": PASSWORD, "password2": PASSWORD, "usable_password": "true"}
        response = self.client.post(reverse("admin:accounts_user_add"), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email="nova@example.com").exists())


class AuthAPITests(APITestCase):
    def setUp(self):
        cache.clear()  # zera os contadores do throttling entre os testes
        self.register_url = reverse("auth-register")
        self.login_url = reverse("auth-login")
        self.logout_url = reverse("auth-logout")
        self.me_url = reverse("auth-me")
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD, first_name="Ana")

    def login(self, email="ana@example.com", password=PASSWORD):
        return self.client.post(self.login_url, {"email": email, "password": password}, format="json")

    def authenticate(self):
        token = self.login().json()["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")

    def test_register_creates_user(self):
        data = {"email": "novo@example.com", "password": PASSWORD, "first_name": "Novo"}
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("password", response.json())
        self.assertTrue(User.objects.filter(email="novo@example.com").exists())

    def test_register_rejects_duplicate_email_ignoring_case(self):
        data = {"email": "ANA@example.com", "password": PASSWORD}
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json())

    def test_register_rejects_weak_password(self):
        data = {"email": "novo@example.com", "password": "12345678"}
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, 400)

    def test_register_ignores_privilege_fields(self):
        data = {"email": "hacker@example.com", "password": PASSWORD, "is_staff": True, "is_superuser": True}
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="hacker@example.com")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_login_returns_token(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.json())

    def test_login_ignores_email_case(self):
        self.assertEqual(self.login(email="ANA@Example.com").status_code, 200)

    def test_login_with_wrong_password_fails(self):
        self.assertEqual(self.login(password="errada").status_code, 400)

    def test_login_with_inactive_user_fails(self):
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.login().status_code, 400)

    def test_me_requires_authentication(self):
        self.assertEqual(self.client.get(self.me_url).status_code, 401)

    def test_me_returns_current_user(self):
        self.authenticate()
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "ana@example.com")

    def test_me_cannot_change_email_or_privileges(self):
        self.authenticate()
        data = {"email": "outro@example.com", "is_staff": True, "first_name": "Ana Maria"}
        response = self.client.patch(self.me_url, data, format="json")
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "ana@example.com")
        self.assertEqual(self.user.first_name, "Ana Maria")
        self.assertFalse(self.user.is_staff)

    def test_logout_invalidates_token(self):
        self.authenticate()
        self.assertEqual(self.client.post(self.logout_url).status_code, 204)
        self.assertEqual(self.client.get(self.me_url).status_code, 401)


class AuthSecurityTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        self.me = reverse("auth-me")

    def tearDown(self):
        cache.clear()  # não deixa contadores de throttling vazarem para outros testes

    def login(self, password=PASSWORD):
        return self.client.post(
            reverse("auth-login"), {"email": "ana@example.com", "password": password}, format="json"
        )

    def token(self):
        return self.login().json()["token"]

    def me_status(self, token, scheme="Token"):
        self.client.credentials(HTTP_AUTHORIZATION=f"{scheme} {token}")
        return self.client.get(self.me).status_code

    def test_logoutall_invalidates_every_token_of_the_user(self):
        first, second = self.token(), self.token()
        self.assertEqual(self.me_status(first), 200)
        self.assertEqual(self.client.post(reverse("auth-logoutall")).status_code, 204)
        self.assertEqual(self.me_status(first), 401)
        self.assertEqual(self.me_status(second), 401)

    def test_expired_token_is_rejected(self):
        token = self.token()
        self.assertEqual(self.me_status(token), 200)
        AuthToken.objects.filter(user=self.user).update(expiry=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.me_status(token), 401)

    def test_other_authorization_schemes_are_not_accepted(self):
        self.assertEqual(self.me_status(self.token(), scheme="Bearer"), 401)

    def test_garbage_token_is_rejected(self):
        self.assertEqual(self.me_status("naoexiste"), 401)

    def test_login_is_throttled_after_five_attempts_in_a_minute(self):
        statuses = [self.login(password="errada").status_code for _ in range(6)]
        self.assertEqual(statuses, [400, 400, 400, 400, 400, 429])

    def test_register_is_throttled_after_ten_attempts_in_an_hour(self):
        url = reverse("auth-register")
        statuses = [
            self.client.post(url, {"email": "x@example.com", "password": "123"}, format="json").status_code
            for _ in range(11)
        ]
        self.assertEqual(statuses, [400] * 10 + [429])


class AnonymizeUserTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD, first_name="Ana", last_name="Silva")

    def test_personal_data_is_removed_and_access_is_closed(self):
        anonymize_user(self.user)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, f"anonimo-{self.user.pk}@anonimo.invalid")
        self.assertEqual((self.user.first_name, self.user.last_name), ("", ""))
        self.assertFalse(self.user.is_active)
        self.assertFalse(self.user.has_usable_password())
        self.assertIsNone(authenticate(email="ana@example.com", password=PASSWORD))

    def test_tokens_and_cart_are_removed(self):
        Cart = apps.get_model("cart", "Cart")
        AuthToken.objects.create(user=self.user)
        Cart.objects.create(user=self.user)
        anonymize_user(self.user)
        self.assertFalse(AuthToken.objects.filter(user=self.user).exists())
        self.assertFalse(Cart.objects.filter(user=self.user).exists())

    def test_order_history_is_preserved(self):
        order = apps.get_model("orders", "Order").objects.create(user=self.user, total="10.00", **SHIPPING)
        anonymize_user(self.user)
        order.refresh_from_db()
        self.assertEqual(order.user_id, self.user.pk)

    def test_original_email_can_register_again(self):
        anonymize_user(self.user)
        self.assertTrue(User.objects.create_user("ana@example.com", password=PASSWORD).is_active)

    def test_running_it_twice_is_harmless(self):
        anonymize_user(self.user)
        anonymize_user(self.user)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_staff_accounts_are_refused(self):
        staff = User.objects.create_user("staff@example.com", password=PASSWORD, is_staff=True)
        with self.assertRaises(ValueError):
            anonymize_user(staff)

    def test_management_command(self):
        out = StringIO()
        call_command("anonymize_user", "ANA@example.com", stdout=out)
        self.assertIn("Conta anonimizada", out.getvalue())
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_management_command_with_unknown_email(self):
        with self.assertRaises(CommandError):
            call_command("anonymize_user", "ninguem@example.com")


ADDRESS = {
    "recipient_name": "Ana Silva",
    "zip_code": "01310100",
    "street": "Avenida Paulista",
    "number": "1000",
    "complement": "apto 12",
    "district": "Bela Vista",
    "city": "São Paulo",
    "state": "sp",
}


class AddressAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        self.other = User.objects.create_user("beto@example.com", password=PASSWORD)
        self.client.force_authenticate(self.user)
        self.url = reverse("address-list")

    def create(self, **extra):
        return self.client.post(self.url, {**ADDRESS, **extra}, format="json")

    def detail(self, pk):
        return reverse("address-detail", kwargs={"pk": pk})

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_create_normalizes_and_first_address_becomes_default(self):
        response = self.create()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual((body["zip_code"], body["state"]), ("01310-100", "SP"))
        self.assertTrue(body["is_default"])

    def test_second_address_is_not_default_unless_requested(self):
        first = self.create().json()
        second = self.create(street="Rua Augusta").json()
        self.assertFalse(second["is_default"])
        third = self.create(street="Rua Oscar Freire", is_default=True).json()
        self.assertTrue(third["is_default"])
        self.assertFalse(Address.objects.get(pk=first["id"]).is_default)
        self.assertEqual(Address.objects.filter(user=self.user, is_default=True).count(), 1)

    def test_list_shows_only_own_addresses(self):
        self.create()
        Address.objects.create(user=self.other, **{**ADDRESS, "state": "RJ"})
        listing = self.client.get(self.url).json()
        self.assertEqual(len(listing), 1)

    def test_cannot_touch_someone_elses_address(self):
        theirs = Address.objects.create(user=self.other, **{**ADDRESS, "state": "RJ"})
        self.assertEqual(self.client.get(self.detail(theirs.pk)).status_code, 404)
        self.assertEqual(self.client.patch(self.detail(theirs.pk), {"city": "X"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(self.detail(theirs.pk)).status_code, 404)

    def test_update_fields(self):
        pk = self.create().json()["id"]
        response = self.client.patch(self.detail(pk), {"number": "2000", "label": "Casa"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json()["number"], response.json()["label"]), ("2000", "Casa"))

    def test_the_default_cannot_be_unset_directly(self):
        pk = self.create().json()["id"]
        response = self.client.patch(self.detail(pk), {"is_default": False}, format="json")
        self.assertTrue(response.json()["is_default"])

    def test_deleting_the_default_promotes_another_address(self):
        first = self.create().json()["id"]
        second = self.create(street="Rua Augusta").json()["id"]
        self.assertEqual(self.client.delete(self.detail(first)).status_code, 204)
        self.assertTrue(Address.objects.get(pk=second).is_default)

    def test_address_limit_per_account(self):
        for i in range(Address.MAX_PER_USER):
            self.assertEqual(self.create(number=str(i)).status_code, 201)
        self.assertEqual(self.create(number="99").status_code, 400)

    def test_invalid_zip_and_state_are_rejected(self):
        self.assertEqual(self.create(zip_code="123").status_code, 400)
        self.assertEqual(self.create(state="Sao").status_code, 400)

    def test_anonymizing_the_account_removes_its_addresses(self):
        self.create()
        anonymize_user(self.user)
        self.assertFalse(Address.objects.filter(user=self.user).exists())


@override_settings(FRONTEND_URL="https://loja.example.com")
class PasswordTests(APITestCase):
    NEW = "Outra-senha-forte-456"

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        self.change_url = reverse("auth-password-change")
        self.reset_url = reverse("auth-password-reset")
        self.confirm_url = reverse("auth-password-reset-confirm")

    def tearDown(self):
        cache.clear()

    def login(self, password):
        return self.client.post(
            reverse("auth-login"), {"email": "ana@example.com", "password": password}, format="json"
        )

    def token(self):
        return self.login(PASSWORD).json()["token"]

    def credentials(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")

    def reset_link_parts(self):
        body = mail.outbox[-1].body
        match = re.search(r"uid=([^&\s]+)&token=(\S+)", body)
        return match.group(1), match.group(2)

    # --- trocar a senha estando logado ---
    def test_change_requires_authentication(self):
        self.assertEqual(self.client.post(self.change_url, {}, format="json").status_code, 401)

    def test_change_password_keeps_this_session_and_closes_the_others(self):
        mine, elsewhere = self.token(), self.token()
        self.credentials(mine)
        data = {"current_password": PASSWORD, "new_password": self.NEW}
        self.assertEqual(self.client.post(self.change_url, data, format="json").status_code, 200)
        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 200)  # esta sessão continua
        self.credentials(elsewhere)
        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 401)  # a outra caiu
        self.client.credentials()
        self.assertEqual(self.login(PASSWORD).status_code, 400)
        self.assertEqual(self.login(self.NEW).status_code, 200)

    def test_change_password_rejects_wrong_current_and_weak_new(self):
        self.credentials(self.token())
        wrong = self.client.post(
            self.change_url, {"current_password": "errada", "new_password": self.NEW}, format="json"
        )
        self.assertEqual((wrong.status_code, "current_password" in wrong.json()), (400, True))
        weak = self.client.post(
            self.change_url, {"current_password": PASSWORD, "new_password": "12345678"}, format="json"
        )
        self.assertEqual((weak.status_code, "new_password" in weak.json()), (400, True))
        self.client.credentials()
        self.assertEqual(self.login(PASSWORD).status_code, 200)  # nada mudou

    # --- esqueci a senha: pedido ---
    def test_reset_request_sends_one_email_with_a_working_link(self):
        response = self.client.post(self.reset_url, {"email": "ANA@example.com"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ana@example.com"])
        self.assertIn("https://loja.example.com/redefinir-senha?uid=", mail.outbox[0].body)

    def test_reset_request_never_reveals_whether_the_account_exists(self):
        known = self.client.post(self.reset_url, {"email": "ana@example.com"}, format="json")
        unknown = self.client.post(self.reset_url, {"email": "ninguem@example.com"}, format="json")
        self.assertEqual((known.status_code, known.json()), (unknown.status_code, unknown.json()))
        self.assertEqual(len(mail.outbox), 1)  # só a conta que existe recebeu

    def test_no_email_for_inactive_or_anonymized_accounts(self):
        inactive = User.objects.create_user("inativa@example.com", password=PASSWORD, is_active=False)
        self.client.post(self.reset_url, {"email": inactive.email}, format="json")
        anonymize_user(self.user)
        self.client.post(self.reset_url, {"email": "ana@example.com"}, format="json")
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_request_is_throttled(self):
        statuses = [
            self.client.post(self.reset_url, {"email": "ana@example.com"}, format="json").status_code for _ in range(6)
        ]
        self.assertEqual(statuses, [200] * 5 + [429])

    # --- esqueci a senha: confirmação ---
    def test_reset_with_the_emailed_link(self):
        old_token = self.token()
        self.client.post(self.reset_url, {"email": "ana@example.com"}, format="json")
        uid, token = self.reset_link_parts()
        response = self.client.post(
            self.confirm_url, {"uid": uid, "token": token, "new_password": self.NEW}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.login(self.NEW).status_code, 200)
        self.assertEqual(self.login(PASSWORD).status_code, 400)
        self.credentials(old_token)
        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 401)  # sessões antigas encerradas

    def test_the_link_works_only_once(self):
        self.client.post(self.reset_url, {"email": "ana@example.com"}, format="json")
        uid, token = self.reset_link_parts()
        data = {"uid": uid, "token": token, "new_password": self.NEW}
        self.assertEqual(self.client.post(self.confirm_url, data, format="json").status_code, 200)
        again = self.client.post(self.confirm_url, {**data, "new_password": "Terceira-senha-789"}, format="json")
        self.assertEqual(again.status_code, 400)

    def test_invalid_token_and_invalid_uid_are_rejected(self):
        self.client.post(self.reset_url, {"email": "ana@example.com"}, format="json")
        uid, token = self.reset_link_parts()
        bad_token = self.client.post(
            self.confirm_url, {"uid": uid, "token": "x" * 30, "new_password": self.NEW}, format="json"
        )
        bad_uid = self.client.post(
            self.confirm_url, {"uid": "naoeumuid", "token": token, "new_password": self.NEW}, format="json"
        )
        self.assertEqual((bad_token.status_code, bad_uid.status_code), (400, 400))
        self.assertEqual(bad_token.json(), bad_uid.json())  # mesma mensagem
        self.assertEqual(self.login(PASSWORD).status_code, 200)

    def test_weak_new_password_is_rejected_and_the_link_keeps_working(self):
        self.client.post(self.reset_url, {"email": "ana@example.com"}, format="json")
        uid, token = self.reset_link_parts()
        weak = self.client.post(
            self.confirm_url, {"uid": uid, "token": token, "new_password": "12345678"}, format="json"
        )
        self.assertEqual((weak.status_code, "new_password" in weak.json()), (400, True))
        ok = self.client.post(self.confirm_url, {"uid": uid, "token": token, "new_password": self.NEW}, format="json")
        self.assertEqual(ok.status_code, 200)

    @override_settings(PASSWORD_RESET_TIMEOUT=-1)
    def test_expired_link_is_rejected(self):
        self.client.post(self.reset_url, {"email": "ana@example.com"}, format="json")
        uid, token = self.reset_link_parts()
        response = self.client.post(
            self.confirm_url, {"uid": uid, "token": token, "new_password": self.NEW}, format="json"
        )
        self.assertEqual(response.status_code, 400)


class PasswordResetQueueTests(TestCase):
    def setUp(self):
        from accounts.tasks import send_password_reset_email_task

        self.task = send_password_reset_email_task
        self.user = User.objects.create_user("ana@example.com", password="Senha-forte-123")

    def test_only_the_user_id_goes_through_the_queue_never_the_token(self):
        from unittest import mock

        from accounts.services import request_password_reset

        with mock.patch.object(self.task, "delay") as delay:
            request_password_reset("ana@example.com")
        delay.assert_called_once_with(self.user.pk)

    def test_unknown_emails_enqueue_nothing(self):
        from unittest import mock

        from accounts.services import request_password_reset

        with mock.patch.object(self.task, "delay") as delay:
            request_password_reset("ninguem@example.com")
        delay.assert_not_called()

    def test_the_link_is_built_when_the_task_runs(self):
        from django.core import mail

        from accounts.services import request_password_reset

        request_password_reset("ana@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/redefinir-senha?uid=", mail.outbox[0].body)

    def test_the_email_is_skipped_if_the_account_was_closed_meanwhile(self):
        from django.core import mail

        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.task.delay(self.user.pk)
        self.assertEqual(len(mail.outbox), 0)
