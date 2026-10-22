import hashlib
import hmac
import json
import threading
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from cart.services import add_item
from orders.models import Order
from orders.services import cancel_order, create_order
from products.models import Category, Product

from .checks import fake_gateway_in_production
from .gateways import FakeGateway, get_gateway
from .models import Payment, WebhookEvent

User = get_user_model()
PASSWORD = "Senha-forte-123"
SECRET = "segredo-de-teste"
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


def make_order(user, quantity=2):
    category, _ = Category.objects.get_or_create(name="Camisetas", slug="camisetas")
    Product.objects.get_or_create(
        slug="camiseta",
        defaults={"name": "Camiseta", "description": "d", "price": "49.90", "stock": 50, "category": category},
    )
    add_item(user, "camiseta", quantity)
    return create_order(user=user, shipping=SHIPPING)


def sign(body):
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def send_event(
    client,
    reference,
    status="approved",
    event_id="evt_1",
    amount=None,
    signature=None,
    provider="fake",
    payment_id=None,
):
    payload = {"event_id": event_id, "reference": reference, "status": status}
    if amount is not None:
        payload["amount"] = str(amount)
    if payment_id is not None:
        payload["payment_id"] = payment_id
    body = json.dumps(payload).encode()
    return client.post(
        reverse("payment-webhook", kwargs={"provider": provider}),
        data=body,
        content_type="application/json",
        HTTP_X_SIGNATURE=signature or sign(body),
    )


@override_settings(PAYMENT_GATEWAY="fake", PAYMENT_WEBHOOK_SECRET=SECRET)
class StartPaymentTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        self.other = User.objects.create_user("beto@example.com", password=PASSWORD)
        self.order = make_order(self.user)  # 2 x 49.90 = 99.80
        self.url = reverse("payment-list")
        self.client.force_authenticate(self.user)

    def pay(self, order=None, method="pix", **extra):
        return self.client.post(self.url, {"order": (order or self.order).pk, "method": method, **extra}, format="json")

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.pay().status_code, 401)

    def test_start_pix_payment(self):
        response = self.pay()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["amount"], "99.80")
        self.assertIn("pix_copy_paste", body["payment_data"])
        self.assertNotIn("provider_reference", body)

    def test_client_cannot_choose_amount_or_status(self):
        body = self.pay(amount="0.01", status="approved").json()
        self.assertEqual(body["amount"], "99.80")
        self.assertEqual(body["status"], "pending")

    def test_cannot_pay_someone_elses_order(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.pay().status_code, 404)

    def test_invalid_method_is_rejected(self):
        self.assertEqual(self.pay(method="cheque").status_code, 400)

    def test_second_payment_while_one_is_pending_is_a_conflict(self):
        self.assertEqual(self.pay().status_code, 201)
        self.assertEqual(self.pay().status_code, 409)
        self.assertEqual(Payment.objects.count(), 1)

    def test_can_retry_after_a_failed_payment(self):
        reference = self.pay().json()["id"]
        payment = Payment.objects.get(pk=reference)
        send_event(APIClient(), payment.provider_reference, status="failed")
        self.assertEqual(self.pay(method="card").status_code, 201)
        self.assertEqual(Payment.objects.count(), 2)

    def test_cannot_pay_cancelled_order(self):
        cancel_order(self.order)
        self.assertEqual(self.pay().status_code, 409)

    def test_gateway_failure_marks_payment_failed_and_allows_retry(self):
        with mock.patch.object(FakeGateway, "create_payment", side_effect=RuntimeError("fora do ar")):
            self.assertEqual(self.pay().status_code, 503)
        self.assertEqual(Payment.objects.get().status, "failed")
        self.assertEqual(self.pay().status_code, 201)

    def test_user_sees_only_own_payments(self):
        payment_id = self.pay().json()["id"]
        self.assertEqual(self.client.get(reverse("payment-detail", kwargs={"pk": payment_id})).status_code, 200)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(reverse("payment-detail", kwargs={"pk": payment_id})).status_code, 404)
        self.assertEqual(self.client.get(self.url).json()["count"], 0)


@override_settings(PAYMENT_GATEWAY="fake", PAYMENT_WEBHOOK_SECRET=SECRET)
class WebhookTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        self.order = make_order(self.user)
        self.client.force_authenticate(self.user)
        self.payment_id = self.client.post(
            reverse("payment-list"), {"order": self.order.pk, "method": "pix"}, format="json"
        ).json()["id"]
        self.reference = Payment.objects.get(pk=self.payment_id).provider_reference
        self.provider = APIClient()  # o provedor não tem login

    def refresh(self):
        self.order.refresh_from_db()
        return Payment.objects.get(pk=self.payment_id)

    def test_approved_event_pays_the_order(self):
        response = send_event(self.provider, self.reference, amount="99.80")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "processed"})
        payment = self.refresh()
        self.assertEqual(payment.status, "approved")
        self.assertIsNotNone(payment.paid_at)
        self.assertFalse(payment.needs_refund)
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_replayed_event_is_idempotent(self):
        send_event(self.provider, self.reference)
        again = send_event(self.provider, self.reference)
        self.assertEqual(again.json(), {"status": "duplicate"})
        self.assertEqual(WebhookEvent.objects.count(), 1)
        self.refresh()
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_invalid_signature_is_rejected_and_changes_nothing(self):
        response = send_event(self.provider, self.reference, signature="0" * 64)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.refresh().status, "pending")
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_missing_secret_rejects_everything(self):
        with override_settings(PAYMENT_WEBHOOK_SECRET=""):
            self.assertEqual(send_event(self.provider, self.reference).status_code, 400)
        self.assertEqual(self.refresh().status, "pending")

    def test_malformed_body_is_rejected(self):
        body = b"isto nao e json"
        response = self.provider.post(
            reverse("payment-webhook", kwargs={"provider": "fake"}),
            data=body,
            content_type="application/json",
            HTTP_X_SIGNATURE=sign(body),
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_provider_is_404(self):
        self.assertEqual(send_event(self.provider, self.reference, provider="outro").status_code, 404)

    def test_unknown_reference_is_not_recorded_so_the_provider_can_retry(self):
        response = send_event(self.provider, "fake_inexistente")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"status": "unmatched"})
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_event_that_arrives_before_the_reference_is_saved_is_processed_on_retry(self):
        # corrida: o provedor avisa antes de gravarmos a referência dele
        Payment.objects.filter(pk=self.payment_id).update(provider_reference="")
        self.assertEqual(send_event(self.provider, self.reference).status_code, 404)
        Payment.objects.filter(pk=self.payment_id).update(provider_reference=self.reference)
        retry = send_event(self.provider, self.reference)  # mesmo event_id
        self.assertEqual(retry.json(), {"status": "processed"})
        self.assertEqual(self.refresh().status, "approved")
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_event_is_matched_by_our_payment_id_when_the_reference_is_still_missing(self):
        Payment.objects.filter(pk=self.payment_id).update(provider_reference="")
        response = send_event(self.provider, self.reference, payment_id=self.payment_id)
        self.assertEqual(response.json(), {"status": "processed"})
        payment = self.refresh()
        self.assertEqual(payment.status, "approved")
        self.assertEqual(payment.provider_reference, self.reference)
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_failed_event_keeps_order_pending(self):
        send_event(self.provider, self.reference, status="failed")
        self.assertEqual(self.refresh().status, "failed")
        self.assertEqual(self.order.status, Order.Status.PENDING)

    def test_late_failure_does_not_undo_an_approval(self):
        send_event(self.provider, self.reference, status="approved", event_id="evt_1")
        response = send_event(self.provider, self.reference, status="failed", event_id="evt_2")
        self.assertEqual(response.json(), {"status": "ignored"})
        self.assertEqual(self.refresh().status, "approved")
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_amount_mismatch_is_not_approved(self):
        response = send_event(self.provider, self.reference, amount="0.01")
        self.assertEqual(response.json(), {"status": "ignored"})
        self.assertEqual(self.refresh().status, "pending")
        self.assertEqual(self.order.status, Order.Status.PENDING)

    def test_cancelling_the_order_cancels_its_pending_payment(self):
        cancel_order(self.order)
        self.assertEqual(self.refresh().status, "cancelled")

    def test_payment_after_cancellation_is_flagged_for_refund(self):
        cancel_order(self.order)
        response = send_event(self.provider, self.reference, status="approved")
        self.assertEqual(response.json(), {"status": "processed"})
        payment = self.refresh()
        self.assertEqual(payment.status, "approved")
        self.assertTrue(payment.needs_refund)
        self.assertEqual(self.order.status, Order.Status.CANCELLED)  # o pedido NÃO é reaberto


@override_settings(PAYMENT_GATEWAY="fake", PAYMENT_WEBHOOK_SECRET=SECRET)
class PaymentConcurrencyTests(TransactionTestCase):
    """Threads com commits reais: só valem em Postgres."""

    def run_parallel(self, job, times=2):
        barrier = threading.Barrier(times)
        results = [None] * times

        def worker(i):
            try:
                barrier.wait()
                results[i] = job()
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(times)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return results

    def test_two_simultaneous_payment_requests_create_one_payment(self):
        user = User.objects.create_user("ana@example.com", password=PASSWORD)
        order = make_order(user)

        def job():
            client = APIClient()
            client.force_authenticate(user)
            return client.post(reverse("payment-list"), {"order": order.pk, "method": "pix"}, format="json").status_code

        self.assertEqual(sorted(self.run_parallel(job)), [201, 409])
        self.assertEqual(Payment.objects.count(), 1)

    def test_same_webhook_delivered_twice_at_once_is_processed_once(self):
        user = User.objects.create_user("ana@example.com", password=PASSWORD)
        order = make_order(user)
        client = APIClient()
        client.force_authenticate(user)
        payment = Payment.objects.get(
            pk=client.post(reverse("payment-list"), {"order": order.pk, "method": "pix"}, format="json").json()["id"]
        )

        def job():
            return send_event(APIClient(), payment.provider_reference).json()["status"]

        self.assertEqual(sorted(self.run_parallel(job)), ["duplicate", "processed"])
        self.assertEqual(WebhookEvent.objects.count(), 1)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)


class GatewayConfigurationTests(SimpleTestCase):
    @override_settings(PAYMENT_GATEWAY="")
    def test_missing_gateway_fails_loudly(self):
        with self.assertRaises(ImproperlyConfigured):
            get_gateway()

    @override_settings(PAYMENT_GATEWAY="inexistente")
    def test_unknown_gateway_fails_loudly(self):
        with self.assertRaises(ImproperlyConfigured):
            get_gateway()

    @override_settings(DEBUG=False, PAYMENT_GATEWAY="fake")
    def test_deploy_check_rejects_the_fake_gateway_in_production(self):
        self.assertEqual([e.id for e in fake_gateway_in_production(None)], ["payments.E001"])

    @override_settings(DEBUG=True, PAYMENT_GATEWAY="fake")
    def test_deploy_check_allows_the_fake_gateway_in_development(self):
        self.assertEqual(fake_gateway_in_production(None), [])
