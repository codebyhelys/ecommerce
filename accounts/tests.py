from datetime import timedelta
from io import StringIO

from django.apps import apps
from django.contrib.auth import authenticate, get_user_model
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from knox.models import AuthToken
from rest_framework.test import APITestCase

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
