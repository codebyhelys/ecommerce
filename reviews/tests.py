from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.services import anonymize_user
from cart.services import add_item
from orders.models import Order
from orders.services import create_order
from products.models import Category, Product

from .models import Review

User = get_user_model()
PASSWORD = "Senha-forte-123"
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


def make_product(slug="camiseta", **extra):
    category, _ = Category.objects.get_or_create(name="Camisetas", slug="camisetas")
    defaults = {"name": slug.title(), "description": "d", "price": "49.90", "stock": 50, "category": category}
    return Product.objects.create(slug=slug, **{**defaults, **extra})


def make_user(email, **extra):
    return User.objects.create_user(email, password=PASSWORD, **extra)


def buy(user, product, status="paid"):
    add_item(user, product.slug, 1)
    order = create_order(user=user, shipping=SHIPPING)
    Order.objects.filter(pk=order.pk).update(status=status)
    return order


class ReviewAPITests(APITestCase):
    def setUp(self):
        self.product = make_product()
        self.buyer = make_user("ana@example.com", first_name="Ana")
        buy(self.buyer, self.product)
        self.url = reverse("review-list", kwargs={"product_slug": "camiseta"})

    def post(self, **data):
        return self.client.post(self.url, {"rating": 5, "comment": "Ótima", **data}, format="json")

    def test_a_buyer_can_review(self):
        self.client.force_authenticate(self.buyer)
        response = self.post()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["rating"], body["comment"], body["author"], body["mine"]), (5, "Ótima", "Ana", True))

    def test_anonymous_cannot_review(self):
        self.assertEqual(self.post().status_code, 401)

    def test_someone_who_never_bought_cannot_review(self):
        self.client.force_authenticate(make_user("bia@example.com"))
        self.assertEqual(self.post().status_code, 403)
        self.assertFalse(Review.objects.exists())

    def test_only_paid_orders_count_as_a_purchase(self):
        other = make_product("bone")
        for status, allowed in [
            ("pending", False),
            ("cancelled", False),
            ("paid", True),
            ("shipped", True),
            ("delivered", True),
        ]:
            user = make_user(f"{status}@example.com")
            buy(user, other, status=status)
            self.client.force_authenticate(user)
            url = reverse("review-list", kwargs={"product_slug": "bone"})
            response = self.client.post(url, {"rating": 4}, format="json")
            self.assertEqual(response.status_code, 201 if allowed else 403, status)

    def test_buying_another_product_does_not_allow_reviewing_this_one(self):
        other = make_product("bone")
        user = make_user("bia@example.com")
        buy(user, other)
        self.client.force_authenticate(user)
        self.assertEqual(self.post().status_code, 403)

    def test_one_review_per_user_and_product(self):
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.post().status_code, 201)
        response = self.post(rating=1)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Review.objects.get().rating, 5)

    def test_rating_must_be_between_1_and_5(self):
        self.client.force_authenticate(self.buyer)
        for bad in (0, 6, -1, "abc", None, 4.5):
            self.assertEqual(self.post(rating=bad).status_code, 400, bad)
        self.assertFalse(Review.objects.exists())

    def test_the_comment_is_optional_and_limited(self):
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.post(self.url, {"rating": 3}, format="json").status_code, 201)
        Review.objects.all().delete()
        self.assertEqual(self.post(comment="x" * 1001).status_code, 400)

    def test_the_database_enforces_the_rating_range(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Review.objects.create(product=self.product, user=self.buyer, rating=9)

    def test_reading_is_public_and_never_leaks_the_email(self):
        Review.objects.create(product=self.product, user=self.buyer, rating=4, comment="Boa")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("ana@example.com", response.content.decode())
        result = response.json()["results"][0]
        self.assertEqual((result["author"], result["mine"]), ("Ana", False))

    def test_author_falls_back_to_a_generic_name(self):
        nameless = make_user("sem-nome@example.com")
        buy(nameless, self.product)
        Review.objects.create(product=self.product, user=nameless, rating=4)
        self.assertEqual(self.client.get(self.url).json()["results"][0]["author"], "Cliente")

    def test_reviews_of_a_hidden_product_are_hidden_from_the_public(self):
        Review.objects.create(product=self.product, user=self.buyer, rating=4)
        Product.objects.filter(pk=self.product.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.force_authenticate(make_user("staff@example.com", is_staff=True))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_unknown_product_is_404(self):
        self.assertEqual(self.client.get(reverse("review-list", kwargs={"product_slug": "nada"})).status_code, 404)


class ReviewEditingTests(APITestCase):
    def setUp(self):
        self.product = make_product()
        self.author = make_user("ana@example.com")
        buy(self.author, self.product)
        self.review = Review.objects.create(product=self.product, user=self.author, rating=3, comment="Ok")
        self.url = reverse("review-detail", kwargs={"product_slug": "camiseta", "pk": self.review.pk})

    def test_the_author_can_edit(self):
        self.client.force_authenticate(self.author)
        response = self.client.patch(self.url, {"rating": 5, "comment": "Melhorou"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.review.refresh_from_db()
        self.assertEqual((self.review.rating, self.review.comment), (5, "Melhorou"))

    def test_put_is_not_allowed(self):
        self.client.force_authenticate(self.author)
        self.assertEqual(self.client.put(self.url, {"rating": 5}, format="json").status_code, 405)

    def test_others_cannot_edit_or_delete_not_even_staff_edit(self):
        for user in (make_user("bia@example.com"), make_user("staff@example.com", is_staff=True)):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.patch(self.url, {"rating": 1}, format="json").status_code, 403)
        self.client.force_authenticate(make_user("carla@example.com"))
        self.assertEqual(self.client.delete(self.url).status_code, 403)
        self.review.refresh_from_db()
        self.assertEqual(self.review.rating, 3)

    def test_the_author_and_staff_can_delete(self):
        self.client.force_authenticate(self.author)
        self.assertEqual(self.client.delete(self.url).status_code, 204)
        review = Review.objects.create(product=self.product, user=self.author, rating=2)
        url = reverse("review-detail", kwargs={"product_slug": "camiseta", "pk": review.pk})
        self.client.force_authenticate(make_user("staff@example.com", is_staff=True))
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertFalse(Review.objects.exists())

    def test_a_review_is_only_reachable_through_its_own_product(self):
        make_product("bone")
        url = reverse("review-detail", kwargs={"product_slug": "bone", "pk": self.review.pk})
        self.assertEqual(self.client.get(url).status_code, 404)


class ProductRatingSummaryTests(APITestCase):
    def setUp(self):
        self.product = make_product()
        self.plain = make_product("bone")
        for email, rating in [("a@example.com", 5), ("b@example.com", 4)]:
            user = make_user(email)
            Review.objects.create(product=self.product, user=user, rating=rating)

    def test_detail_shows_average_and_count(self):
        body = self.client.get(reverse("product-detail", kwargs={"slug": "camiseta"})).json()
        self.assertEqual((body["rating_average"], body["reviews_count"]), (4.5, 2))

    def test_a_product_without_reviews_has_no_average(self):
        body = self.client.get(reverse("product-detail", kwargs={"slug": "bone"})).json()
        self.assertEqual((body["rating_average"], body["reviews_count"]), (None, 0))

    def test_listing_carries_the_summary_without_extra_queries_per_product(self):
        def count_queries():
            with CaptureQueriesContext(connection) as ctx:
                response = self.client.get(reverse("product-list"))
            return len(ctx), {p["slug"]: p["reviews_count"] for p in response.json()["results"]}

        baseline, counts = count_queries()
        self.assertEqual(counts, {"camiseta": 2, "bone": 0})
        for i in range(5):
            extra = make_product(f"extra-{i}")
            Review.objects.create(product=extra, user=make_user(f"x{i}@example.com"), rating=3)
        self.assertEqual(count_queries()[0], baseline)

    def test_the_review_list_does_not_query_per_review(self):
        url = reverse("review-list", kwargs={"product_slug": "camiseta"})

        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(url)
            return len(ctx)

        baseline = count()
        for i in range(5):
            Review.objects.create(product=self.product, user=make_user(f"y{i}@example.com"), rating=3)
        self.assertEqual(count(), baseline)


class ReviewPrivacyTests(TestCase):
    def test_anonymizing_an_account_removes_its_reviews(self):
        product = make_product()
        user = make_user("ana@example.com")
        Review.objects.create(product=product, user=user, rating=5, comment="Meu telefone é 11 99999-9999")
        anonymize_user(user)
        self.assertFalse(Review.objects.exists())
