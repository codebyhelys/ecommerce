from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from .models import Category, Product
from .serializers import ProductSerializer


class ProductModelTests(TestCase):
    def test_negative_price_is_invalid(self):
        category = Category.objects.create(name="Camisetas", slug="camisetas")
        product = Product(
            name="Camiseta",
            slug="camiseta",
            description="Camiseta básica",
            price=-1,
            category=category,
        )
        with self.assertRaises(ValidationError) as ctx:
            product.full_clean()
        self.assertIn("price", ctx.exception.message_dict)


class ProductAPITests(APITestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Camisetas", slug="camisetas")
        self.product = Product.objects.create(
            name="Camisa Ativa", slug="camiseta-ativa", price=10, category=self.category
        )
        Product.objects.create(
            name="Camiseta Oculta", slug="camiseta-oculta", price=10, category=self.category, is_active=False
        )
        self.staff = get_user_model().objects.create_user("staff", password="senha-teste", is_staff=True)
        self.list_url = reverse("product-list")
        self.detail_url = reverse("product-detail", kwargs={"slug": "camiseta-ativa"})

    def test_public_list_shows_only_active_product(self):
        response = self.client.get(self.list_url)
        self.assertContains(response, "camiseta-ativa")
        self.assertNotContains(response, "camiseta-oculta")

    def test_public_can_retrieve_active_product(self):
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["slug"], "camiseta-ativa")

    def test_public_cannot_retrieve_inactive_product(self):
        url = reverse("product-detail", kwargs={"slug": "camiseta-oculta"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_anonymous_cannot_create(self):
        response = self.client.post(self.list_url, {}, format="json")
        self.assertIn(response.status_code, (401, 403))

    def test_staff_can_create(self):
        self.client.force_authenticate(self.staff)
        data = {
            "name": "Nova",
            "slug": "nova",
            "description": "Camiseta nova",
            "price": "20.00",
            "category_id": self.category.pk,
        }
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, 201)

    def test_negative_price_is_rejected_by_api(self):
        self.client.force_authenticate(self.staff)
        data = {
            "name": "Nova",
            "slug": "nova",
            "description": "Camiseta nova",
            "price": "-5.00",
            "category_id": self.category.pk,
        }
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("price", response.json())

    def test_delete_deactivates_product(self):
        self.client.force_authenticate(self.staff)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, 204)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)


User = get_user_model()
PASSWORD = "Senha-forte-123"


def make_product(category, slug, price, name=None, description="descricao", **extra):
    return Product.objects.create(
        name=name or slug.replace("-", " ").title(),
        slug=slug,
        description=description,
        price=Decimal(price),
        stock=extra.pop("stock", 10),
        category=category,
        **extra,
    )


class CategoryAPITests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user("staff@example.com", password=PASSWORD, is_staff=True)
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        self.category = Category.objects.create(name="Camisetas", slug="camisetas")
        self.url = reverse("category-list")
        self.detail = reverse("category-detail", kwargs={"slug": "camisetas"})

    def test_public_list_is_a_plain_list_counting_only_active_products(self):
        make_product(self.category, "ativa", "10")
        make_product(self.category, "oculta", "10", is_active=False)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), [{"id": self.category.pk, "name": "Camisetas", "slug": "camisetas", "products_count": 1}]
        )

    def test_only_staff_can_create(self):
        data = {"name": "Bonés", "slug": "bones"}
        self.assertEqual(self.client.post(self.url, data, format="json").status_code, 401)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.post(self.url, data, format="json").status_code, 403)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.post(self.url, data, format="json").status_code, 201)

    def test_deleting_a_category_with_products_is_a_conflict(self):
        make_product(self.category, "camiseta", "10")
        self.client.force_authenticate(self.staff)
        response = self.client.delete(self.detail)
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())

    def test_deleting_an_empty_category_works(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.delete(self.detail).status_code, 204)
        self.assertFalse(Category.objects.filter(pk=self.category.pk).exists())

    def test_regular_user_cannot_delete(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.delete(self.detail).status_code, 403)


class ProductPermissionTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user("staff@example.com", password=PASSWORD, is_staff=True)
        self.user = User.objects.create_user("ana@example.com", password=PASSWORD)
        self.category = Category.objects.create(name="Camisetas", slug="camisetas")
        self.product = make_product(self.category, "camiseta", "49.90")
        self.list_url = reverse("product-list")
        self.detail = reverse("product-detail", kwargs={"slug": "camiseta"})

    def test_anonymous_cannot_write(self):
        self.assertEqual(self.client.post(self.list_url, {}, format="json").status_code, 401)
        self.assertEqual(self.client.patch(self.detail, {"price": "1.00"}, format="json").status_code, 401)
        self.assertEqual(self.client.delete(self.detail).status_code, 401)

    def test_regular_user_cannot_write(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.post(self.list_url, {}, format="json").status_code, 403)
        self.assertEqual(self.client.patch(self.detail, {"price": "1.00"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(self.detail).status_code, 403)

    def test_staff_can_update(self):
        self.client.force_authenticate(self.staff)
        response = self.client.patch(self.detail, {"price": "59.90"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.price, Decimal("59.90"))

    def test_options_is_public_on_every_catalog_endpoint(self):
        for url in (self.list_url, self.detail, reverse("category-list")):
            self.assertEqual(self.client.options(url).status_code, 200, url)

    def test_editing_other_fields_does_not_overwrite_stock_changed_meanwhile(self):
        stale = Product.objects.get(pk=self.product.pk)  # o staff abre o produto (estoque 10)
        Product.objects.filter(pk=self.product.pk).update(stock=7)  # um checkout baixa 3 unidades
        serializer = ProductSerializer(stale, data={"price": "12.00"}, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        fresh = Product.objects.get(pk=self.product.pk)
        self.assertEqual(fresh.stock, 7)
        self.assertEqual(fresh.price, Decimal("12.00"))


class ProductListingTests(APITestCase):
    def setUp(self):
        self.shirts = Category.objects.create(name="Camisetas", slug="camisetas")
        self.pants = Category.objects.create(name="Calças", slug="calcas")
        make_product(self.shirts, "camiseta-basica", "29.90", description="algodão macio")
        make_product(self.shirts, "camiseta-estampada", "59.90", description="estampa exclusiva")
        make_product(self.pants, "calca-jeans", "149.90", description="jeans azul")
        self.url = reverse("product-list")

    def slugs(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200, response.content)
        return [p["slug"] for p in response.json()["results"]]

    def test_default_order_is_newest_first(self):
        self.assertEqual(self.slugs(), ["calca-jeans", "camiseta-estampada", "camiseta-basica"])

    def test_filter_by_category(self):
        self.assertEqual(set(self.slugs(category="camisetas")), {"camiseta-basica", "camiseta-estampada"})
        self.assertEqual(self.slugs(category="calcas"), ["calca-jeans"])

    def test_filter_by_price_range(self):
        self.assertEqual(self.slugs(min_price="50", max_price="100"), ["camiseta-estampada"])
        self.assertEqual(self.slugs(min_price="100"), ["calca-jeans"])

    def test_search_matches_name_and_description(self):
        self.assertEqual(self.slugs(search="jeans"), ["calca-jeans"])
        self.assertEqual(self.slugs(search="algodão"), ["camiseta-basica"])

    def test_ordering_by_price(self):
        self.assertEqual(self.slugs(ordering="price"), ["camiseta-basica", "camiseta-estampada", "calca-jeans"])
        self.assertEqual(self.slugs(ordering="-price"), ["calca-jeans", "camiseta-estampada", "camiseta-basica"])

    def test_ordering_by_a_field_that_is_not_allowed_is_ignored(self):
        self.assertEqual(self.slugs(ordering="stock"), ["calca-jeans", "camiseta-estampada", "camiseta-basica"])

    def test_filters_combine(self):
        self.assertEqual(self.slugs(category="camisetas", max_price="40", search="camiseta"), ["camiseta-basica"])

    def test_invalid_price_is_a_bad_request(self):
        self.assertEqual(self.client.get(self.url, {"min_price": "abc"}).status_code, 400)

    def test_results_are_paginated(self):
        for i in range(10):
            make_product(self.shirts, f"extra-{i}", "10")
        first = self.client.get(self.url).json()
        self.assertEqual(first["count"], 13)
        self.assertEqual(len(first["results"]), 12)
        self.assertIsNotNone(first["next"])
        second = self.client.get(self.url, {"page": 2}).json()
        self.assertEqual(len(second["results"]), 1)
        self.assertIsNone(second["next"])


class ProductAdminActionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("root@example.com", password=PASSWORD)
        self.client.force_login(self.admin)
        category = Category.objects.create(name="Camisetas", slug="camisetas")
        self.active = make_product(category, "ativa", "10")
        self.hidden = make_product(category, "oculta", "10", is_active=False)
        self.changelist = reverse("admin:products_product_changelist")

    def run_action(self, action, *products):
        data = {"action": action, "_selected_action": [p.pk for p in products]}
        return self.client.post(self.changelist, data, follow=True)

    def test_deactivate_and_activate_actions(self):
        self.run_action("deactivate", self.active)
        self.active.refresh_from_db()
        self.assertFalse(self.active.is_active)
        self.run_action("activate", self.hidden)
        self.hidden.refresh_from_db()
        self.assertTrue(self.hidden.is_active)
