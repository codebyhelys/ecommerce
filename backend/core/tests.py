import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

User = get_user_model()


class GlobalThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.products = reverse("product-list")

    def tearDown(self):
        cache.clear()  # não deixa contadores baixos vazarem para outros testes

    @override_settings(THROTTLE_ANON_RATE="3/min")
    def test_anonymous_clients_are_limited(self):
        statuses = [self.client.get(self.products).status_code for _ in range(4)]
        self.assertEqual(statuses, [200, 200, 200, 429])

    @override_settings(THROTTLE_USER_RATE="2/min", THROTTLE_ANON_RATE="1000/min")
    def test_logged_in_users_have_their_own_limit(self):
        user = User.objects.create_user("ana@example.com", password="Senha-forte-123")
        self.client.force_authenticate(user)
        statuses = [self.client.get(self.products).status_code for _ in range(3)]
        self.assertEqual(statuses, [200, 200, 429])
        # outro cliente anônimo não é afetado pelo limite do usuário
        self.assertEqual(APIClient().get(self.products).status_code, 200)

    @override_settings(THROTTLE_ANON_RATE="1/min")
    def test_webhook_is_not_throttled(self):
        url = reverse("payment-webhook", kwargs={"provider": "fake"})
        statuses = {self.client.post(url, data=b"{}", content_type="application/json").status_code for _ in range(5)}
        self.assertNotIn(429, statuses)


ALLOWED_ORIGIN = "https://loja.example.com"


@override_settings(CORS_ALLOWED_ORIGINS=[ALLOWED_ORIGIN])
class CorsTests(SimpleTestCase):
    def preflight(self, origin, path="/api/products/"):
        return self.client.options(
            path,
            HTTP_ORIGIN=origin,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization",
        )

    def test_the_configured_front_end_is_allowed(self):
        response = self.preflight(ALLOWED_ORIGIN)
        self.assertEqual(response["Access-Control-Allow-Origin"], ALLOWED_ORIGIN)
        self.assertIn("authorization", response["Access-Control-Allow-Headers"])

    def test_other_origins_get_no_cors_headers(self):
        self.assertNotIn("Access-Control-Allow-Origin", self.preflight("https://evil.example.com"))

    def test_credentials_are_never_enabled(self):
        # a API usa token no cabeçalho; liberar cookies entre origens só ampliaria o risco de CSRF
        self.assertNotIn("Access-Control-Allow-Credentials", self.preflight(ALLOWED_ORIGIN))

    def test_only_the_api_is_exposed_to_other_origins(self):
        self.assertNotIn("Access-Control-Allow-Origin", self.preflight(ALLOWED_ORIGIN, path="/admin/login/"))

    @override_settings(CORS_ALLOWED_ORIGINS=[])
    def test_no_origins_by_default_means_no_cors(self):
        self.assertNotIn("Access-Control-Allow-Origin", self.preflight(ALLOWED_ORIGIN))


class ApiDocsTests(SimpleTestCase):
    def test_the_schema_endpoint_serves_openapi(self):
        response = self.client.get(reverse("schema"), {"format": "json"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("/api/products/", response.json()["paths"])

    def test_the_docs_page_loads(self):
        self.assertEqual(self.client.get(reverse("docs")).status_code, 200)

    def test_the_schema_has_no_warnings(self):
        # views novas sem anotação (serializer/resposta) quebram aqui, em vez de sumirem da documentação
        with tempfile.TemporaryDirectory() as folder:
            call_command("spectacular", "--validate", "--fail-on-warn", "--file", str(Path(folder) / "schema.yml"))


class HealthTests(TestCase):
    def test_reports_ok_when_the_database_answers(self):
        response = self.client.get(reverse("health"))
        self.assertEqual((response.status_code, response.json()), (200, {"status": "ok"}))

    def test_reports_unavailable_when_the_database_is_down(self):
        with mock.patch("core.views.connection.cursor", side_effect=OperationalError("fora do ar")):
            response = self.client.get(reverse("health"))
        self.assertEqual((response.status_code, response.json()), (503, {"status": "unavailable"}))

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_the_probe_is_not_redirected_to_https_but_the_api_is(self):
        self.assertEqual(self.client.get(reverse("health")).status_code, 200)
        self.assertEqual(self.client.get(reverse("product-list")).status_code, 301)

    def test_it_is_not_throttled(self):
        with override_settings(THROTTLE_ANON_RATE="1/min"):
            statuses = {self.client.get(reverse("health")).status_code for _ in range(3)}
        self.assertEqual(statuses, {200})
