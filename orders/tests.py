import threading
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from accounts.models import Address
from cart.models import Cart
from cart.services import add_item
from payments.models import Payment
from products.models import Category, Product

from .emails import build_order_email
from .models import Order
from .services import (
    InvalidOrderState,
    cancel_order,
    cancel_paid_order,
    create_order,
    deliver_order,
    expire_pending_orders,
    ship_order,
)

User = get_user_model()
PASSWORD = "Senha-forte-123"

SHIPPING = {
    "shipping_name": "Ana Silva",
    "shipping_zip_code": "01310-100",
    "shipping_street": "Avenida Paulista",
    "shipping_number": "1000",
    "shipping_complement": "apto 12",
    "shipping_district": "Bela Vista",
    "shipping_city": "São Paulo",
    "shipping_state": "SP",
}


def make_catalog():
    category = Category.objects.create(name="Camisetas", slug="camisetas")
    shirt = Product.objects.create(
        name="Camiseta", slug="camiseta", description="d", price=Decimal("49.90"), stock=5, category=category
    )
    cap = Product.objects.create(
        name="Boné", slug="bone", description="d", price=Decimal("30.00"), stock=2, category=category
    )
    return shirt, cap


@override_settings(SHIPPING_FLAT_RATE=Decimal("0.00"))  # estes testes tratam só do valor dos itens
class OrderAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        self.other = User.objects.create_user("beto@example.com", password=PASSWORD)
        self.staff = User.objects.create_user("staff@example.com", password=PASSWORD, is_staff=True)
        self.shirt, self.cap = make_catalog()
        self.url = reverse("order-list")
        self.client.force_authenticate(self.user)

    def checkout(self, **overrides):
        return self.client.post(self.url, {**SHIPPING, **overrides}, format="json")

    def fill_cart(self, user=None, shirt=2, cap=0):
        user = user or self.user
        if shirt:
            add_item(user, "camiseta", shirt)
        if cap:
            add_item(user, "bone", cap)

    # --- criação ---
    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.checkout().status_code, 401)

    def test_checkout_creates_order_from_cart(self):
        self.fill_cart(shirt=2, cap=1)
        response = self.checkout()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["total"], "129.80")  # 2 x 49.90 + 30.00
        self.assertEqual({i["product"]: i["quantity"] for i in body["items"]}, {"camiseta": 2, "bone": 1})
        self.assertEqual(body["shipping_city"], "São Paulo")

    def test_checkout_decrements_stock_and_empties_cart(self):
        self.fill_cart(shirt=2, cap=1)
        self.checkout()
        self.shirt.refresh_from_db()
        self.cap.refresh_from_db()
        self.assertEqual((self.shirt.stock, self.cap.stock), (3, 1))
        self.assertFalse(Cart.objects.get(user=self.user).items.exists())

    def test_order_keeps_the_price_paid_after_product_changes(self):
        self.fill_cart(shirt=1)
        order_id = self.checkout().json()["id"]
        self.shirt.price = Decimal("99.90")
        self.shirt.name = "Camiseta Nova"
        self.shirt.save()
        body = self.client.get(reverse("order-detail", kwargs={"pk": order_id})).json()
        self.assertEqual(body["total"], "49.90")
        self.assertEqual(body["items"][0]["unit_price"], "49.90")
        self.assertEqual(body["items"][0]["product_name"], "Camiseta")

    def test_empty_cart_is_rejected(self):
        response = self.checkout()
        self.assertEqual(response.status_code, 400)
        self.assertIn("cart", response.json())
        self.assertEqual(Order.objects.count(), 0)

    def test_insufficient_stock_rejects_everything_atomically(self):
        self.fill_cart(shirt=2, cap=2)
        self.cap.stock = 1  # alguém comprou antes
        self.cap.save()
        response = self.checkout()
        self.assertEqual(response.status_code, 400)
        self.assertIn("items", response.json())
        self.shirt.refresh_from_db()
        self.assertEqual(self.shirt.stock, 5)  # o item bom NAO foi baixado
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Cart.objects.get(user=self.user).items.count(), 2)  # carrinho intacto

    def test_inactive_product_in_cart_is_rejected(self):
        self.fill_cart(shirt=1)
        self.shirt.is_active = False
        self.shirt.save()
        self.assertEqual(self.checkout().status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_shipping_is_validated_and_normalized(self):
        self.fill_cart(shirt=1)
        self.assertEqual(self.checkout(shipping_zip_code="123").status_code, 400)
        self.assertEqual(self.checkout(shipping_state="Sao").status_code, 400)
        self.assertEqual(self.checkout(shipping_name="").status_code, 400)
        body = self.checkout(shipping_zip_code="01310100", shipping_state="sp").json()
        self.assertEqual(body["shipping_zip_code"], "01310-100")
        self.assertEqual(body["shipping_state"], "SP")

    def test_client_cannot_set_status_or_total(self):
        self.fill_cart(shirt=1)
        body = self.checkout(status="paid", total="0.01", user=self.other.pk).json()
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["total"], "49.90")
        self.assertEqual(Order.objects.get().user, self.user)

    # --- leitura ---
    def test_user_sees_only_own_orders(self):
        self.fill_cart(self.user, shirt=1)
        mine = self.checkout().json()["id"]
        self.client.force_authenticate(self.other)
        self.fill_cart(self.other, shirt=1)
        theirs = self.checkout().json()["id"]
        listing = self.client.get(self.url).json()
        self.assertEqual([o["id"] for o in listing["results"]], [theirs])
        self.assertEqual(self.client.get(reverse("order-detail", kwargs={"pk": mine})).status_code, 404)

    def test_staff_sees_all_orders(self):
        self.fill_cart(self.user, shirt=1)
        self.checkout()
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get(self.url).json()["count"], 1)

    def test_list_does_not_do_n_plus_one(self):
        for _ in range(3):
            self.fill_cart(shirt=1)
            self.checkout()
        with CaptureQueriesContext(connection) as queries:
            self.client.get(self.url)
        self.assertLessEqual(len(queries), 3)  # contagem + pedidos + itens

    # --- cancelamento ---
    def test_cancel_restores_stock(self):
        self.fill_cart(shirt=2, cap=1)
        order_id = self.checkout().json()["id"]
        response = self.client.post(reverse("order-cancel", kwargs={"pk": order_id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "cancelled")
        self.shirt.refresh_from_db()
        self.cap.refresh_from_db()
        self.assertEqual((self.shirt.stock, self.cap.stock), (5, 2))

    def test_cancel_twice_is_a_conflict_and_does_not_restore_twice(self):
        self.fill_cart(shirt=2)
        order_id = self.checkout().json()["id"]
        url = reverse("order-cancel", kwargs={"pk": order_id})
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertEqual(self.client.post(url).status_code, 409)
        self.shirt.refresh_from_db()
        self.assertEqual(self.shirt.stock, 5)

    def test_only_pending_orders_can_be_cancelled(self):
        self.fill_cart(shirt=1)
        order = Order.objects.get(pk=self.checkout().json()["id"])
        order.status = Order.Status.PAID
        order.save()
        response = self.client.post(reverse("order-cancel", kwargs={"pk": order.pk}))
        self.assertEqual(response.status_code, 409)

    def test_cannot_cancel_someone_elses_order(self):
        self.fill_cart(shirt=1)
        order_id = self.checkout().json()["id"]
        self.client.force_authenticate(self.other)
        response = self.client.post(reverse("order-cancel", kwargs={"pk": order_id}))
        self.assertEqual(response.status_code, 404)


class OrderConcurrencyTests(TransactionTestCase):
    """Rodam com commits reais e threads: só fazem sentido em Postgres (select_for_update)."""

    def run_in_threads(self, jobs):
        barrier = threading.Barrier(len(jobs))
        results = [None] * len(jobs)

        def worker(index, user):
            try:
                client = APIClient()
                client.force_authenticate(user)
                barrier.wait()
                results[index] = client.post(reverse("order-list"), SHIPPING, format="json").status_code
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(i, u)) for i, u in enumerate(jobs)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return sorted(results)

    def test_two_buyers_one_last_unit(self):
        shirt, _ = make_catalog()
        shirt.stock = 1
        shirt.save()
        users = [User.objects.create_user(f"u{i}@example.com", password=PASSWORD) for i in range(2)]
        for u in users:
            add_item(u, "camiseta", 1)

        self.assertEqual(self.run_in_threads(users), [201, 400])
        shirt.refresh_from_db()
        self.assertEqual(shirt.stock, 0)
        self.assertEqual(Order.objects.count(), 1)

    def test_double_checkout_of_same_cart_creates_one_order(self):
        shirt, _ = make_catalog()
        user = User.objects.create_user("ana@example.com", password=PASSWORD)
        add_item(user, "camiseta", 2)

        self.assertEqual(self.run_in_threads([user, user]), [201, 400])
        shirt.refresh_from_db()
        self.assertEqual(shirt.stock, 3)  # baixou uma vez só
        self.assertEqual(Order.objects.count(), 1)


class ExpirationTests(TestCase):
    """Pedidos que ninguém paga não podem segurar o estoque para sempre."""

    def setUp(self):
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        self.shirt, _ = make_catalog()  # estoque inicial: 5

    def make_order(self, minutes_old=0):
        add_item(self.user, "camiseta", 2)
        order = create_order(user=self.user, shipping=SHIPPING)
        Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(minutes=minutes_old))
        return order

    def add_payment(self, order, minutes_old, reference="ref_1"):
        payment = Payment.objects.create(
            order=order, provider="fake", method="pix", amount=order.total, provider_reference=reference
        )
        Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(minutes=minutes_old))
        return payment

    def status(self, order):
        order.refresh_from_db()
        return order.status

    def test_old_pending_order_is_cancelled_and_stock_returns(self):
        order = self.make_order(minutes_old=120)
        self.shirt.refresh_from_db()
        self.assertEqual(self.shirt.stock, 3)
        self.assertEqual(expire_pending_orders(), (1, 0))
        self.assertEqual(self.status(order), "cancelled")
        self.shirt.refresh_from_db()
        self.assertEqual(self.shirt.stock, 5)

    def test_recent_pending_order_is_left_alone(self):
        order = self.make_order(minutes_old=10)
        self.assertEqual(expire_pending_orders(), (0, 0))
        self.assertEqual(self.status(order), "pending")

    def test_order_with_a_payment_still_in_progress_is_left_alone(self):
        order = self.make_order(minutes_old=120)
        self.add_payment(order, minutes_old=5)  # Pix gerado há 5 min, ainda válido
        self.assertEqual(expire_pending_orders(), (0, 0))
        self.assertEqual(self.status(order), "pending")

    def test_order_whose_payment_window_has_passed_expires_and_the_payment_is_cancelled(self):
        order = self.make_order(minutes_old=120)
        payment = self.add_payment(order, minutes_old=45)
        self.assertEqual(expire_pending_orders(), (1, 0))
        self.assertEqual(self.status(order), "cancelled")
        payment.refresh_from_db()
        self.assertEqual(payment.status, "cancelled")

    def test_paid_orders_are_never_expired(self):
        order = self.make_order(minutes_old=500)
        Order.objects.filter(pk=order.pk).update(status="paid")
        self.assertEqual(expire_pending_orders(), (0, 0))
        self.assertEqual(self.status(order), "paid")

    def test_payment_never_sent_to_the_provider_is_released_so_the_order_can_expire(self):
        order = self.make_order(minutes_old=120)
        payment = self.add_payment(order, minutes_old=30, reference="")  # caiu entre criar e chamar o provedor
        self.assertEqual(expire_pending_orders(), (1, 1))
        payment.refresh_from_db()
        self.assertEqual(payment.status, "failed")
        self.assertEqual(self.status(order), "cancelled")

    def test_management_command_reports_what_it_did(self):
        self.make_order(minutes_old=120)
        out = StringIO()
        call_command("expire_pending_orders", stdout=out)
        self.assertIn("1 pedido(s) expirado(s)", out.getvalue())


class OrderStatusTransitionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        make_catalog()
        add_item(self.user, "camiseta", 1)
        self.order = create_order(user=self.user, shipping=SHIPPING)

    def set_status(self, status):
        Order.objects.filter(pk=self.order.pk).update(status=status)

    def test_full_lifecycle(self):
        self.set_status("paid")
        self.assertEqual(ship_order(self.order).status, "shipped")
        self.assertEqual(deliver_order(self.order).status, "delivered")

    def test_cannot_ship_an_unpaid_order(self):
        with self.assertRaises(InvalidOrderState):
            ship_order(self.order)

    def test_cannot_deliver_before_shipping(self):
        self.set_status("paid")
        with self.assertRaises(InvalidOrderState):
            deliver_order(self.order)


class OrderAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("root@example.com", password=PASSWORD)
        self.client.force_login(self.admin)
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        self.shirt, _ = make_catalog()
        self.changelist = reverse("admin:orders_order_changelist")

    def new_order(self, status="pending"):
        add_item(self.user, "camiseta", 1)
        order = create_order(user=self.user, shipping=SHIPPING)
        Order.objects.filter(pk=order.pk).update(status=status)
        return order

    def run_action(self, action, *orders):
        data = {"action": action, "_selected_action": [o.pk for o in orders]}
        return self.client.post(self.changelist, data, follow=True)

    def status(self, order):
        order.refresh_from_db()
        return order.status

    def test_status_cannot_be_edited_by_hand(self):
        order = self.new_order()
        url = reverse("admin:orders_order_change", args=[order.pk])
        self.assertNotContains(self.client.get(url), 'name="status"')
        self.client.post(url, {"status": "cancelled"})
        self.assertEqual(self.status(order), "pending")

    def test_orders_cannot_be_deleted_in_admin(self):
        order = self.new_order()
        response = self.client.get(reverse("admin:orders_order_delete", args=[order.pk]))
        self.assertEqual(response.status_code, 403)

    def test_ship_action_only_moves_paid_orders(self):
        paid, pending = self.new_order("paid"), self.new_order("pending")
        self.run_action("mark_shipped", paid, pending)
        self.assertEqual(self.status(paid), "shipped")
        self.assertEqual(self.status(pending), "pending")

    def test_deliver_action_only_moves_shipped_orders(self):
        shipped, paid = self.new_order("shipped"), self.new_order("paid")
        self.run_action("mark_delivered", shipped, paid)
        self.assertEqual(self.status(shipped), "delivered")
        self.assertEqual(self.status(paid), "paid")

    def test_cancel_action_returns_stock_and_ignores_paid_orders(self):
        pending, paid = self.new_order("pending"), self.new_order("paid")
        self.shirt.refresh_from_db()
        stock_before = self.shirt.stock
        self.run_action("cancel_orders", pending, paid)
        self.assertEqual(self.status(pending), "cancelled")
        self.assertEqual(self.status(paid), "paid")
        self.shirt.refresh_from_db()
        self.assertEqual(self.shirt.stock, stock_before + 1)


class OrderWithSavedAddressTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        self.other = User.objects.create_user("beto@example.com", password=PASSWORD)
        make_catalog()
        self.address = Address.objects.create(
            user=self.user,
            recipient_name="Maria Souza",
            zip_code="20040-020",
            street="Rua da Assembleia",
            number="10",
            complement="sala 3",
            district="Centro",
            city="Rio de Janeiro",
            state="RJ",
        )
        self.url = reverse("order-list")
        self.client.force_authenticate(self.user)
        add_item(self.user, "camiseta", 1)

    def test_checkout_with_a_saved_address_copies_it_into_the_order(self):
        response = self.client.post(self.url, {"address": self.address.pk}, format="json")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["shipping_name"], "Maria Souza")
        self.assertEqual(body["shipping_city"], "Rio de Janeiro")
        self.assertEqual(body["shipping_complement"], "sala 3")
        # editar o endereço depois não altera o pedido já feito
        Address.objects.filter(pk=self.address.pk).update(city="Niterói")
        self.assertEqual(Order.objects.get().shipping_city, "Rio de Janeiro")

    def test_someone_elses_address_is_rejected(self):
        theirs = Address.objects.create(
            user=self.other,
            recipient_name="X",
            zip_code="20040-020",
            street="R",
            number="1",
            district="C",
            city="Rio",
            state="RJ",
        )
        for pk in (theirs.pk, 999999):
            response = self.client.post(self.url, {"address": pk}, format="json")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["address"], ["Endereço inválido."])  # sem revelar se existe
        self.assertEqual(Order.objects.count(), 0)

    def test_without_address_and_without_fields_lists_what_is_missing(self):
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("shipping_zip_code", response.json())
        self.assertNotIn("shipping_complement", response.json())  # opcional

    def test_saved_address_wins_over_loose_fields(self):
        data = {"address": self.address.pk, "shipping_city": "Outra Cidade"}
        self.client.post(self.url, data, format="json")
        self.assertEqual(Order.objects.get().shipping_city, "Rio de Janeiro")


@override_settings(SHIPPING_FLAT_RATE=Decimal("19.90"), SHIPPING_FREE_ABOVE=Decimal("100.00"))
class OrderShippingTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        make_catalog()  # camiseta 49.90, boné 30.00
        self.client.force_authenticate(self.user)
        self.url = reverse("order-list")

    def checkout(self):
        return self.client.post(self.url, SHIPPING, format="json").json()

    def test_below_the_threshold_the_flat_rate_is_charged(self):
        add_item(self.user, "camiseta", 1)  # 49.90
        order = self.checkout()
        self.assertEqual(
            (order["subtotal"], order["discount"], order["shipping_cost"], order["total"]),
            ("49.90", "0.00", "19.90", "69.80"),
        )

    def test_at_or_above_the_threshold_shipping_is_free(self):
        add_item(self.user, "camiseta", 2)  # 99.80 -> ainda abaixo
        add_item(self.user, "bone", 1)  # + 30.00 = 129.80
        order = self.checkout()
        self.assertEqual((order["shipping_cost"], order["total"]), ("0.00", "129.80"))

    @override_settings(SHIPPING_FREE_ABOVE=None)
    def test_free_shipping_can_be_disabled(self):
        add_item(self.user, "camiseta", 2)
        add_item(self.user, "bone", 1)
        self.assertEqual(self.checkout()["shipping_cost"], "19.90")

    def test_the_shipping_paid_is_frozen_in_the_order(self):
        add_item(self.user, "camiseta", 1)
        order = self.checkout()
        with override_settings(SHIPPING_FLAT_RATE=Decimal("99.00")):
            again = self.client.get(reverse("order-detail", kwargs={"pk": order["id"]})).json()
        self.assertEqual(again["shipping_cost"], "19.90")

    def test_the_payment_amount_includes_shipping(self):
        add_item(self.user, "camiseta", 1)
        order_id = self.checkout()["id"]
        self.assertEqual(Order.objects.get(pk=order_id).total, Decimal("69.80"))


@override_settings(SHIPPING_FLAT_RATE=Decimal("10.00"), SHIPPING_FREE_ABOVE=None)
class OrderEmailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        make_catalog()
        add_item(self.user, "camiseta", 2)  # 99.80 + frete 10.00

    def place(self):
        with self.captureOnCommitCallbacks(execute=True):
            return create_order(user=self.user, shipping=SHIPPING)

    def test_order_creation_sends_a_confirmation(self):
        order = self.place()
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual((message.to, message.subject), (["ana@example.com"], f"Recebemos o seu pedido #{order.pk}"))
        for text in ("2 x Camiseta", "Subtotal: R$ 99,80", "Frete: R$ 10,00", "Total: R$ 109,80", "Avenida Paulista"):
            self.assertIn(text, message.body)

    def test_nothing_is_sent_when_the_transaction_does_not_commit(self):
        # sem executar os callbacks de commit (como numa transação que falhou) nada sai
        create_order(user=self.user, shipping=SHIPPING)
        self.assertEqual(len(mail.outbox), 0)

    def test_cancellation_sends_an_email(self):
        order = self.place()
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            cancel_order(order)
        self.assertEqual([m.subject for m in mail.outbox], [f"Pedido #{order.pk} cancelado"])

    def test_shipping_email_carries_the_tracking_code(self):
        order = self.place()
        Order.objects.filter(pk=order.pk).update(status="paid", tracking_code="BR123456789")
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            ship_order(order)
        self.assertIn("Código de rastreio: BR123456789", mail.outbox[0].body)
        with self.captureOnCommitCallbacks(execute=True):
            deliver_order(order)
        self.assertEqual(mail.outbox[-1].subject, f"Seu pedido #{order.pk} foi entregue")

    def test_a_coupon_discount_appears_in_the_email(self):
        order = self.place()
        Order.objects.filter(pk=order.pk).update(discount=Decimal("9.98"), coupon_code="PROMO10")
        order.refresh_from_db()
        _, body = build_order_email(order, "created")
        self.assertIn("Desconto (PROMO10): -R$ 9,98", body)

    def test_an_email_failure_never_breaks_the_order(self):
        with mock.patch("orders.emails.send_mail", side_effect=OSError("SMTP fora do ar")):
            order = self.place()  # não levanta
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())

    def test_closed_accounts_receive_nothing(self):
        order = self.place()
        mail.outbox.clear()
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        order.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            cancel_order(order)
        self.assertEqual(len(mail.outbox), 0)


class OrderAdminTrackingTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("root@example.com", password=PASSWORD)
        self.client.force_login(self.admin)
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        make_catalog()
        add_item(self.user, "camiseta", 1)
        self.order = create_order(user=self.user, shipping=SHIPPING)
        Order.objects.filter(pk=self.order.pk).update(status="paid")

    def test_tracking_code_is_editable_but_money_fields_are_not(self):
        html = self.client.get(reverse("admin:orders_order_change", args=[self.order.pk])).content.decode()
        self.assertIn('name="tracking_code"', html)
        for field in ("total", "subtotal", "discount", "shipping_cost", "status"):
            self.assertNotIn(f'name="{field}"', html)

    def test_shipping_from_the_admin_sends_the_stored_tracking_code(self):
        Order.objects.filter(pk=self.order.pk).update(tracking_code="BR999")
        data = {"action": "mark_shipped", "_selected_action": [self.order.pk]}
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("admin:orders_order_changelist"), data, follow=True)
        self.assertIn("Código de rastreio: BR999", mail.outbox[-1].body)


@override_settings(SHIPPING_FLAT_RATE=Decimal("0.00"))
class CancelPaidOrderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        make_catalog()
        add_item(self.user, "camiseta", 2)
        self.order = create_order(user=self.user, shipping=SHIPPING)
        self.payment = Payment.objects.create(
            order=self.order,
            provider="fake",
            method="pix",
            status="approved",
            amount=self.order.total,
            provider_reference="ref-1",
            paid_at=timezone.now(),
        )
        Order.objects.filter(pk=self.order.pk).update(status="paid")
        self.stock_after_purchase = Product.objects.get(slug="camiseta").stock

    def test_cancelling_returns_stock_and_flags_the_refund(self):
        with self.captureOnCommitCallbacks(execute=True):
            cancel_paid_order(self.order)
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(Product.objects.get(slug="camiseta").stock, self.stock_after_purchase + 2)
        self.assertEqual((self.payment.status, self.payment.needs_refund), ("approved", True))
        self.assertEqual(mail.outbox[-1].subject, f"Pedido #{self.order.pk} cancelado")

    def test_only_paid_orders_can_be_cancelled_this_way(self):
        for status in ("pending", "shipped", "delivered", "cancelled"):
            Order.objects.filter(pk=self.order.pk).update(status=status)
            with self.assertRaises(InvalidOrderState, msg=status):
                cancel_paid_order(self.order)
        self.payment.refresh_from_db()
        self.assertFalse(self.payment.needs_refund)
        self.assertEqual(Product.objects.get(slug="camiseta").stock, self.stock_after_purchase)

    def test_the_regular_cancellation_still_refuses_paid_orders(self):
        with self.assertRaises(InvalidOrderState):
            cancel_order(self.order)

    def test_admin_action_cancels_paid_orders(self):
        admin_user = User.objects.create_superuser("root@example.com", password=PASSWORD)
        self.client.force_login(admin_user)
        data = {"action": "cancel_paid_orders", "_selected_action": [self.order.pk]}
        self.client.post(reverse("admin:orders_order_changelist"), data, follow=True)
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertTrue(self.payment.needs_refund)


class OrderEmailTaskTests(TestCase):
    def setUp(self):
        from .emails import deliver_order_email
        from .tasks import expire_pending_orders_task, send_order_email_task

        self.deliver, self.task, self.expire_task = (
            deliver_order_email,
            send_order_email_task,
            expire_pending_orders_task,
        )
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        make_catalog()
        add_item(self.user, "camiseta", 1)
        self.order = create_order(user=self.user, shipping=SHIPPING)

    def test_the_task_arguments_are_plain_json(self):
        import json

        json.dumps([self.order.pk, "created"])  # o broker só leva tipos simples: nunca o objeto Order

    def test_a_task_for_a_deleted_order_is_a_no_op(self):
        self.deliver(999999, "created")  # não levanta
        self.assertEqual(len(mail.outbox), 0)

    def test_failures_are_retried_until_the_limit_and_then_dropped(self):
        with mock.patch("orders.emails.send_mail", side_effect=OSError("SMTP fora do ar")) as send:
            self.task.delay(self.order.pk, "created")
        self.assertEqual(send.call_count, self.task.max_retries + 1)
        self.assertEqual(len(mail.outbox), 0)

    def test_a_transient_failure_is_retried_and_the_email_goes_out(self):
        real_send = mail.send_mail
        calls = {"n": 0}

        def flaky(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] < 3:
                raise OSError("falha momentânea")
            return real_send(*args, **kwargs)

        with mock.patch("orders.emails.send_mail", side_effect=flaky):
            self.task.delay(self.order.pk, "created")
        self.assertEqual((calls["n"], len(mail.outbox)), (3, 1))

    def test_when_the_broker_is_down_the_email_is_sent_inline(self):
        from .emails import send_order_email

        with mock.patch.object(self.task, "delay", side_effect=ConnectionError("broker fora do ar")):
            send_order_email(self.order, "created")
        self.assertEqual([m.subject for m in mail.outbox], [f"Recebemos o seu pedido #{self.order.pk}"])

    def test_when_both_the_broker_and_smtp_are_down_nothing_raises(self):
        from .emails import send_order_email

        with (
            mock.patch.object(self.task, "delay", side_effect=ConnectionError("broker")),
            mock.patch("orders.emails.send_mail", side_effect=OSError("smtp")),
        ):
            send_order_email(self.order, "created")  # só registra no log

    def test_the_expiration_task_cancels_old_pending_orders(self):
        Order.objects.filter(pk=self.order.pk).update(created_at=timezone.now() - timedelta(hours=3))
        self.expire_task.delay()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)

    def test_the_expiration_runs_every_five_minutes_in_the_schedule(self):
        from django.conf import settings

        entry = settings.CELERY_BEAT_SCHEDULE["expire-pending-orders"]
        self.assertEqual((entry["task"], entry["schedule"]), ("orders.expire_pending_orders", 300.0))
        from core.celery import app

        self.assertIn(entry["task"], app.tasks)
