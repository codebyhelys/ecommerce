from django.db.models import Avg, Count, Q
from django.db.models.deletion import ProtectedError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from .filters import ProductFilter
from .models import Category, Product, ProductImage
from .permissions import IsAdminOrReadOnly
from .serializers import CategorySerializer, ProductImageSerializer, ProductSerializer


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = "slug"
    filterset_class = ProductFilter
    search_fields = ["name", "description"]
    ordering_fields = ["price", "created_at", "name"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = (
            Product.objects.select_related("category")
            .prefetch_related("images")
            .annotate(reviews_count=Count("reviews"), rating_average=Avg("reviews__rating"))
        )
        if not self.request.user.is_staff:
            qs = qs.filter(is_active=True)
        return qs

    def perform_destroy(self, instance):
        # soft delete: desativa em vez de apagar, para preservar o histórico de pedidos
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])

    @action(detail=True, methods=["post"], url_path="images", parser_classes=[MultiPartParser, FormParser])
    def add_image(self, request, slug=None):
        product = self.get_object()
        count = product.images.count()
        if count >= ProductImage.MAX_PER_PRODUCT:
            raise ValidationError({"image": f"Limite de {ProductImage.MAX_PER_PRODUCT} imagens por produto."})
        serializer = ProductImageSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        extra = {} if "position" in request.data else {"position": count}  # sem posição: vai para o fim
        serializer.save(product=product, **extra)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path=r"images/(?P<image_id>\d+)")
    def remove_image(self, request, slug=None, image_id=None):
        product = self.get_object()
        deleted, _ = product.images.filter(pk=image_id).delete()
        if not deleted:
            raise NotFound("Imagem não encontrada.")
        return Response(status=status.HTTP_204_NO_CONTENT)


class CategoryInUse(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Categoria possui produtos e não pode ser removida."
    default_code = "category_in_use"


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = "slug"
    pagination_class = None

    def get_queryset(self):
        return Category.objects.annotate(products_count=Count("products", filter=Q(products__is_active=True))).order_by(
            "name"
        )

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise CategoryInUse() from None
