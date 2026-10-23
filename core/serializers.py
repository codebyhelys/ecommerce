from rest_framework import serializers


class DetailSerializer(serializers.Serializer):
    """Corpo simples `{"detail": "..."}` usado em respostas de confirmação e de erro."""

    detail = serializers.CharField()
