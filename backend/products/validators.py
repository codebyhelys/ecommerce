from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image

ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


def validate_image_size(file):
    limit = settings.PRODUCT_IMAGE_MAX_BYTES
    if file.size > limit:
        raise ValidationError(f"A imagem deve ter no máximo {limit / 1024 / 1024:g} MB.", code="image_too_large")


def validate_image_format(file):
    try:
        with Image.open(file) as image:
            image_format = image.format
    except Exception:
        return  # arquivo que não é imagem: o próprio ImageField já recusa com a mensagem apropriada
    finally:
        file.seek(0)
    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError("Formato não suportado. Envie JPEG, PNG ou WEBP.", code="image_format")
