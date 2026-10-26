from django.http import Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import mixins, permissions, serializers, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .gateways import InvalidWebhook, UnknownGateway
from .models import Payment
from .serializers import PaymentCreateSerializer, PaymentSerializer


class PaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # geração do esquema OpenAPI, sem usuário
            return Payment.objects.none()
        qs = Payment.objects.all()
        if not self.request.user.is_staff:
            qs = qs.filter(order__user=self.request.user)
        return qs

    @extend_schema(request=PaymentCreateSerializer, responses={201: PaymentSerializer})
    def create(self, request):
        serializer = PaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = services.start_payment(
            user=request.user,
            order_id=serializer.validated_data["order"],
            method=serializer.validated_data["method"],
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class WebhookView(APIView):
    """Chamado pelo provedor, não pelo usuário: sem login; a autenticidade vem da assinatura."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = []  # o provedor pode mandar rajadas; a proteção aqui é a assinatura

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses=inline_serializer("WebhookResult", {"status": serializers.CharField()}),
    )
    def post(self, request, provider):
        try:
            result = services.handle_webhook(provider, request.headers, request.body)
        except UnknownGateway:
            raise Http404 from None
        except InvalidWebhook:
            return Response({"detail": "Webhook inválido."}, status=status.HTTP_400_BAD_REQUEST)
        if result == "unmatched":
            # não é erro do provedor: ele deve reenviar o evento mais tarde
            return Response({"status": result}, status=status.HTTP_404_NOT_FOUND)
        return Response({"status": result})
