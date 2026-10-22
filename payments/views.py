from django.http import Http404
from rest_framework import mixins, permissions, status, viewsets
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
        qs = Payment.objects.all()
        if not self.request.user.is_staff:
            qs = qs.filter(order__user=self.request.user)
        return qs

    def create(self, request):
        serializer = PaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = services.start_payment(
            user = request.user,
            order_id=serializer.validated_data["order"],
            method=serializer.validated_data["method"],
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

class WebhookView(APIView):
    """Chamado pelo provedor, não pelo usuário: sem login; a autenticidade vem da assinatura."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request, provider):
        try:
            result = services.handle_webhook(provider, request.headers, request.body)
        except UnknownGateway:
            raise Http404
        except InvalidWebhook:
            return Response({"detail": "Webhook inválido."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"status": result})
