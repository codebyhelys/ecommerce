from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APITestCase

from products.models import Category, Product

from .models import Cart, CartItem

User = get_user_model()
PASSWORD = "Senha-forte-123"


class CartModelTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        category = Category.objects.create(name="Camisetas", slug="camisetas")
        self.product = Product.objects.create(
            name="Camiseta", slug="camiseta", description="d", price=Decimal("10.00"), stock=5, category=category
        )

    def test_one_cart_per_user(self):
        Cart.objects.create(user=self.user)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cart.objects.create(user=self.user)

    def test_item_is_unique_per_cart_and_quantity_must_be_positive(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CartItem.objects.create(cart=cart, product=self.product, quantity=2)
        other = Cart.objects.create(user=User.objects.create_user("beto@example.com", password=PASSWORD))
        with self.assertRaises(IntegrityError), transaction.atomic():
            CartItem.objects.create(cart=other, product=self.product, quantity=0)


class CartAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        self.other = User.objects.create_user("beto@example.com", password=PASSWORD)
        category = Category.objects.create(name="Camisetas", slug="camisetas")
        self.shirt = Product.objects.create(
            name="Camiseta", slug="camiseta", description="d", price=Decimal("49.90"), stock=5, category=category
        )
        self.cap = Product.objects.create(
            name="Boné", slug="bone", description="d", price=Decimal("30.00"), stock=2, category=category
        )
        self.cart_url = reverse("cart")
        self.add_url = reverse("cart-item-add")
        self.client.force_authenticate(self.user)

    def detail_url(self, slug):
        return reverse("cart-item-detail", kwargs={"slug": slug})

    def add(self, slug, quantity=1):
        return self.client.post(self.add_url, {"product": slug, "quantity": quantity}, format="json")

    # --- acesso ---
    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.cart_url).status_code, 401)
        self.assertEqual(self.add("camiseta").status_code, 401)

    def test_first_get_returns_empty_cart(self):
        response = self.client.get(self.cart_url)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["items"], [])
        self.assertEqual(body["items_count"], 0)
        self.assertEqual(body["total"], "0.00")

    def test_carts_are_isolated_between_users(self):
        self.add("camiseta", 2)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.cart_url).json()["items"], [])
        self.assertEqual(self.client.patch(self.detail_url("camiseta"), {"quantity": 1}, format="json").status_code, 404)

    # --- adicionar ---
    def test_add_item(self):
        response = self.add("camiseta", 2)
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["items_count"], 2)
        self.assertEqual(body["total"], "99.80")
        self.assertEqual(body["items"][0]["product"]["slug"], "camiseta")
        self.assertEqual(body["items"][0]["subtotal"], "99.80")

    def test_adding_same_product_sums_quantity(self):
        self.add("camiseta", 2)
        body = self.add("camiseta", 1).json()
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["items"][0]["quantity"], 3)

    def test_quantity_defaults_to_one(self):
        response = self.client.post(self.add_url, {"product": "camiseta"}, format="json")
        self.assertEqual(response.json()["items_count"], 1)

    def test_add_rejects_unknown_or_inactive_product(self):
        self.assertEqual(self.add("nao-existe").status_code, 400)
        self.cap.is_active = False
        self.cap.save()
        self.assertEqual(self.add("bone").status_code, 400)

    def test_add_rejects_more_than_stock_even_when_summed(self):
        self.assertEqual(self.add("bone", 3).status_code, 400)  # estoque 2
        self.assertEqual(self.add("bone", 2).status_code, 201)
        response = self.add("bone", 1)  # 2 + 1 > 2
        self.assertEqual(response.status_code, 400)
        self.assertIn("quantity", response.json())

    def test_add_rejects_invalid_quantity(self):
        self.assertEqual(self.add("camiseta", 0).status_code, 400)
        self.assertEqual(self.add("camiseta", -1).status_code, 400)

    # --- alterar / remover ---
    def test_patch_sets_quantity(self):
        self.add("camiseta", 1)
        response = self.client.patch(self.detail_url("camiseta"), {"quantity": 4}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["quantity"], 4)

    def test_patch_rejects_more_than_stock(self):
        self.add("bone", 1)
        response = self.client.patch(self.detail_url("bone"), {"quantity": 3}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_patch_missing_item_is_404(self):
        response = self.client.patch(self.detail_url("camiseta"), {"quantity": 1}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_delete_item_returns_updated_cart(self):
        self.add("camiseta", 1)
        self.add("bone", 1)
        response = self.client.delete(self.detail_url("camiseta"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([i["product"]["slug"] for i in response.json()["items"]], ["bone"])
        self.assertEqual(self.client.delete(self.detail_url("camiseta")).status_code, 404)

    def test_clear_cart(self):
        self.add("camiseta", 1)
        self.assertEqual(self.client.delete(self.cart_url).status_code, 204)
        self.assertEqual(self.client.get(self.cart_url).json()["items"], [])

    # --- disponibilidade ---
    def test_unavailable_items_are_flagged_and_excluded_from_total(self):
        self.add("camiseta", 1)
        self.add("bone", 2)
        self.cap.stock = 1  # ficou com menos do que o carrinho pede
        self.cap.save()
        body = self.client.get(self.cart_url).json()
        flags = {i["product"]["slug"]: i["available"] for i in body["items"]}
        self.assertEqual(flags, {"camiseta": True, "bone": False})
        self.assertEqual(body["total"], "49.90")
        self.assertEqual(body["items_count"], 3)

    def test_deactivated_product_is_flagged(self):
        self.add("camiseta", 1)
        self.shirt.is_active = False
        self.shirt.save()
        body = self.client.get(self.cart_url).json()
        self.assertFalse(body["items"][0]["available"])
        self.assertEqual(body["total"], "0.00")
        response = self.client.patch(self.detail_url("camiseta"), {"quantity": 2}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_price_is_always_the_current_one(self):
        self.add("camiseta", 1)
        self.shirt.price = Decimal("59.90")
        self.shirt.save()
        self.assertEqual(self.client.get(self.cart_url).json()["total"], "59.90")

    # --- desempenho ---
    def test_cart_read_does_not_do_n_plus_one(self):
        self.add("camiseta", 1)
        self.add("bone", 1)
        with CaptureQueriesContext(connection) as queries:
            self.client.get(self.cart_url)
        self.assertLessEqual(len(queries), 2)