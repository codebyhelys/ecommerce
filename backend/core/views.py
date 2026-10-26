from django.db import OperationalError, connection
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView


@extend_schema(exclude=True)
class HealthView(APIView):
    """Sonda para balanceador/orquestrador: 200 se o app responde e o banco está acessível."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = []  # sondas são frequentes; a rota não expõe nada

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except OperationalError:
            return Response({"status": "unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"status": "ok"})
