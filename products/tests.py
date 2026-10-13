from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from .models import Category, Product


class ProductModelTests(TestCase):
    def test_negative_price_is_invalid(self):
        category = Category.objects.create(name="Camisetas", slug="camisetas")
        product = Product(
            name="Camiseta", slug="camiseta", description="Camiseta básica",
            price=-1, category=category,
        )
        with self.assertRaises(ValidationError) as ctx:
            product.full_clean()
        self.assertIn("price", ctx.exception.message_dict)


class ProductAPITests(APITestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Camisetas", slug="camisetas")
        self.product = Product.objects.create(name="Camisa Ativa", slug="camiseta-ativa", price=10, category=self.category)
        Product.objects.create(name="Camiseta Oculta", slug="camiseta-oculta", price=10, category=self.category, is_active=False)
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
            "name": "Nova", "slug": "nova", "description": "Camiseta nova",
            "price": "20.00", "category_id": self.category.pk,
        }
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, 201)

    def test_negative_price_is_rejected_by_api(self):
        self.client.force_authenticate(self.staff)
        data = {
            "name": "Nova", "slug": "nova", "description": "Camiseta nova",
            "price": "-5.00", "category_id": self.category.pk,
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
