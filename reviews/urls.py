from django.urls import path

from .views import ReviewViewSet

urlpatterns = [
    path(
        "products/<slug:product_slug>/reviews/",
        ReviewViewSet.as_view({"get": "list", "post": "create"}),
        name="review-list",
    ),
    path(
        "products/<slug:product_slug>/reviews/<int:pk>/",
        ReviewViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="review-detail",
    ),
]
