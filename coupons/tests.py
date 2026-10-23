import threading
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from cart.services import add_item
from orders.models import Order
from orders.services import cancel_order
from products.models import Category, Product

from .models import Coupon, CouponRedemption

User = get_user_model()
PASSWORD = "Senha-forte-123"
SHIPPING = {
    "shipping_name": "Ana Silva",
    "shipping_zip_code": "01310-100",
    "shipping_street": "Avenida Paulista",
    "shipping_number": "1000",
    "shipping_district": "Bela Vista",
    "shipping_city": "São Paulo",
    "shipping_state": "SP",
}


def make_product(stock=50):
    category, _ = Category.objects.get_or_create(name="Camisetas", slug="camisetas")
    product, _ = Product.objects.get_or_create(
        slug="camiseta",
        defaults={
            "name": "Camiseta",
            "description": "d",
            "price": Decimal("49.90"),
            "stock": stock,
            "category": category,
        },
    )
    return product


def make_coupon(code="PROMO10", **extra):
    data = {"kind": "percent", "value": Decimal("10.00")}
    data.update(extra)
    return Coupon.objects.create(code=code, **data)


@override_settings(SHIPPING_FLAT_RATE=Decimal("0.00"))
class CouponCheckoutTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        self.other = User.objects.create_user("beto@example.com", password=PASSWORD)
        make_product()
        self.client.force_authenticate(self.user)
        self.url = reverse("order-list")
        add_item(self.user, "camiseta", 2)  # subtotal 99.80

    def checkout(self, code="PROMO10", **extra):
        return self.client.post(self.url, {**SHIPPING, "coupon": code, **extra}, format="json")

    def error(self, response):
        self.assertEqual(response.status_code, 400)
        return (
            response.json()["coupon"][0] if isinstance(response.json()["coupon"], list) else response.json()["coupon"]
        )

    def test_percent_coupon(self):
        make_coupon()
        body = self.checkout().json()
        self.assertEqual(
            (body["subtotal"], body["discount"], body["total"], body["coupon_code"]),
            ("99.80", "9.98", "89.82", "PROMO10"),
        )
        self.assertEqual(CouponRedemption.objects.count(), 1)

    def test_fixed_coupon(self):
        make_coupon("MENOS20", kind="fixed", value=Decimal("20.00"))
        body = self.checkout("MENOS20").json()
        self.assertEqual((body["discount"], body["total"]), ("20.00", "79.80"))

    def test_code_is_case_insensitive_and_trimmed(self):
        make_coupon()
        self.assertEqual(self.checkout(" promo10 ").status_code, 201)

    def test_percent_discount_respects_the_cap(self):
        make_coupon(value=Decimal("50.00"), max_discount=Decimal("15.00"))
        self.assertEqual(self.checkout().json()["discount"], "15.00")

    def test_a_coupon_never_makes_the_order_free(self):
        make_coupon("GRATIS", kind="fixed", value=Decimal("500.00"))
        body = self.checkout("GRATIS").json()
        self.assertEqual((body["discount"], body["total"]), ("99.79", "0.01"))

    def test_unknown_and_inactive_codes_give_the_same_message(self):
        make_coupon("OFF", is_active=False)
        self.assertEqual(self.error(self.checkout("NAOEXISTE")), "Cupom inválido.")
        self.assertEqual(self.error(self.checkout("OFF")), "Cupom inválido.")
        self.assertEqual(Order.objects.count(), 0)

    def test_minimum_order_value(self):
        make_coupon(min_order_value=Decimal("150.00"))
        self.assertIn("Pedido mínimo", self.error(self.checkout()))

    def test_validity_window(self):
        make_coupon("FUTURO", starts_at=timezone.now() + timedelta(days=1))
        make_coupon("VENCIDO", expires_at=timezone.now() - timedelta(minutes=1))
        self.assertIn("ainda não", self.error(self.checkout("FUTURO")))
        self.assertIn("expirou", self.error(self.checkout("VENCIDO")))

    def test_total_usage_limit(self):
        make_coupon(usage_limit=1)
        self.assertEqual(self.checkout().status_code, 201)
        self.client.force_authenticate(self.other)
        add_item(self.other, "camiseta", 1)
        self.assertIn("esgotou", self.error(self.checkout()))

    def test_per_user_limit(self):
        make_coupon()
        self.assertEqual(self.checkout().status_code, 201)
        add_item(self.user, "camiseta", 1)
        self.assertIn("já usou", self.error(self.checkout()))

    def test_cancelling_the_order_gives_the_coupon_back(self):
        make_coupon(usage_limit=1)
        order = Order.objects.get(pk=self.checkout().json()["id"])
        cancel_order(order)
        self.assertEqual(CouponRedemption.objects.count(), 0)
        add_item(self.user, "camiseta", 1)
        self.assertEqual(self.checkout().status_code, 201)

    def test_a_failed_checkout_does_not_consume_the_coupon(self):
        make_coupon(usage_limit=1)
        Product.objects.filter(slug="camiseta").update(stock=1)  # o carrinho pede 2
        self.assertEqual(self.checkout().status_code, 400)
        self.assertEqual(CouponRedemption.objects.count(), 0)

    @override_settings(SHIPPING_FLAT_RATE=Decimal("19.90"), SHIPPING_FREE_ABOVE=Decimal("95.00"))
    def test_discount_can_bring_the_order_below_the_free_shipping_threshold(self):
        make_coupon(value=Decimal("10.00"))  # 99.80 - 9.98 = 89.82 < 95
        body = self.checkout().json()
        self.assertEqual((body["shipping_cost"], body["total"]), ("19.90", "109.72"))

    def test_order_without_coupon_is_unaffected(self):
        body = self.client.post(self.url, SHIPPING, format="json").json()
        self.assertEqual((body["discount"], body["coupon_code"]), ("0.00", ""))


@override_settings(SHIPPING_FLAT_RATE=Decimal("19.90"), SHIPPING_FREE_ABOVE=None)
class CouponPreviewTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        make_product()
        self.client.force_authenticate(self.user)
        self.url = reverse("coupon-validate")

    def tearDown(self):
        cache.clear()

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(self.url, {"code": "X"}, format="json").status_code, 401)

    def test_preview_does_not_use_the_coupon(self):
        make_coupon()
        add_item(self.user, "camiseta", 2)
        body = self.client.post(self.url, {"code": "promo10"}, format="json").json()
        self.assertEqual(
            (body["code"], body["subtotal"], body["discount"], body["shipping_cost"], body["total"]),
            ("PROMO10", "99.80", "9.98", "19.90", "109.72"),
        )
        self.assertEqual(CouponRedemption.objects.count(), 0)

    def test_invalid_code_and_empty_cart(self):
        add_item(self.user, "camiseta", 1)
        response = self.client.post(self.url, {"code": "NADA"}, format="json")
        self.assertEqual((response.status_code, response.json()["coupon"]), (400, "Cupom inválido."))
        from cart.services import clear_cart

        clear_cart(self.user)
        self.assertEqual(self.client.post(self.url, {"code": "NADA"}, format="json").status_code, 400)

    def test_guessing_codes_is_throttled(self):
        statuses = [self.client.post(self.url, {"code": f"X{i}"}, format="json").status_code for i in range(21)]
        self.assertEqual(statuses[-1], 429)
        self.assertNotIn(429, statuses[:20])


class CouponModelTests(APITestCase):
    def test_code_is_stored_uppercase(self):
        self.assertEqual(make_coupon(" verao ").code, "VERAO")

    def test_percent_above_100_is_rejected_by_the_database(self):
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError), transaction.atomic():
            make_coupon("MUITO", value=Decimal("150.00"))

    def test_fixed_value_may_exceed_100(self):
        self.assertEqual(make_coupon("CINCO", kind="fixed", value=Decimal("150.00")).value, Decimal("150.00"))


@override_settings(SHIPPING_FLAT_RATE=Decimal("0.00"))
class CouponConcurrencyTests(TransactionTestCase):
    """Dois clientes tentando usar o último uso do cupom ao mesmo tempo (só vale em Postgres)."""

    def test_only_one_checkout_gets_the_last_use(self):
        make_product()
        make_coupon(usage_limit=1)
        users = [User.objects.create_user(f"u{i}@example.com", password=PASSWORD) for i in range(2)]
        for u in users:
            add_item(u, "camiseta", 1)
        barrier = threading.Barrier(2)
        results = [None, None]

        def worker(index, user):
            try:
                client = APIClient()
                client.force_authenticate(user)
                barrier.wait()
                results[index] = client.post(
                    reverse("order-list"), {**SHIPPING, "coupon": "PROMO10"}, format="json"
                ).status_code
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(i, u)) for i, u in enumerate(users)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(results), [201, 400])
        self.assertEqual(CouponRedemption.objects.count(), 1)
