"""Popula o banco de TESTE DE CARGA com produtos, usuários, avaliações e tokens.

Uso (a partir da pasta backend, com o banco criado e migrado):

    DB_NAME=ecommerce_load python loadtest/seed.py

Recusa rodar em qualquer banco que não se chame `ecommerce_load`, para nunca poluir o de desenvolvimento.
Grava `loadtest/tokens.json` (ignorado pelo git): um token de acesso por usuário de teste.
"""

import json
import os
import random
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from knox.models import AuthToken  # noqa: E402

from products.models import Category, Product  # noqa: E402
from reviews.models import Review  # noqa: E402

PRODUCTS = 5000
CATEGORIES = 20
USERS = 400
REVIEWS_PER_USER = 60
STOCK = 1_000_000

ADJECTIVES = ["Básica", "Premium", "Esportiva", "Clássica", "Leve", "Térmica", "Casual", "Estampada", "Lisa", "Slim"]
NOUNS = ["Camiseta", "Calça", "Jaqueta", "Bermuda", "Moletom", "Boné", "Meia", "Tênis", "Mochila", "Relógio"]

name = settings.DATABASES["default"]["NAME"]
if name != "ecommerce_load":
    sys.exit(f"Recusado: o banco é '{name}'. Rode com DB_NAME=ecommerce_load.")
if Product.objects.exists():
    sys.exit("O banco já tem produtos. Recrie-o (veja loadtest/README.md) antes de popular de novo.")

random.seed(42)
User = get_user_model()

categories = Category.objects.bulk_create(
    [Category(name=f"Categoria {i}", slug=f"categoria-{i}") for i in range(1, CATEGORIES + 1)]
)

products = []
for i in range(1, PRODUCTS + 1):
    noun, adjective = random.choice(NOUNS), random.choice(ADJECTIVES)
    products.append(
        Product(
            name=f"{noun} {adjective} {i}",
            slug=f"produto-{i:05d}",
            description=f"{noun} {adjective.lower()} de boa qualidade, modelo {i}.",
            price=random.randint(1000, 50000) / 100,
            stock=STOCK,
            category=categories[i % CATEGORIES],
        )
    )
# produtos dos cenários de contenção
products.append(
    Product(
        name="Produto Quente",
        slug="produto-quente",
        description="Estoque enorme, todos compram o mesmo.",
        price=19.90,
        stock=100_000_000,
        category=categories[0],
    )
)
products.append(
    Product(
        name="Produto Limitado",
        slug="produto-limitado",
        description="Só 300 unidades: não pode vender a mais.",
        price=29.90,
        stock=300,
        category=categories[0],
    )
)
Product.objects.bulk_create(products, batch_size=1000)

users = User.objects.bulk_create(
    [User(email=f"carga{i}@example.com", password="!") for i in range(1, USERS + 1)]  # sem senha utilizável
)

sample = list(Product.objects.filter(slug__startswith="produto-0")[:REVIEWS_PER_USER])
Review.objects.bulk_create(
    [Review(product=p, user=u, rating=random.randint(1, 5), comment="ok") for u in users for p in sample],
    batch_size=2000,
)

tokens = [AuthToken.objects.create(user=u, expiry=timedelta(days=1))[1] for u in users]
(ROOT / "loadtest" / "tokens.json").write_text(json.dumps(tokens), encoding="utf-8")

print(f"produtos={Product.objects.count()} usuarios={User.objects.count()}", end=" ")
print(f"avaliacoes={Review.objects.count()} tokens={len(tokens)}")
