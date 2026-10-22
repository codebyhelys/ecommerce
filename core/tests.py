from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
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
