from rest_framework import serializers


class CouponCodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=40)
