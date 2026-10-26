# E-commerce

Loja virtual em dois projetos no mesmo repositório:

| Pasta | O que é | Stack |
|---|---|---|
| [`backend/`](backend/README.md) | API REST: catálogo, contas, carrinho, cupons, frete, pedidos, pagamentos, avaliações | Django 6, Django REST Framework, PostgreSQL, Redis, Celery |
| [`frontend/`](frontend/README.md) | Interface web | Next.js 16, React 19, TypeScript, Tailwind CSS 4 |

## Como rodar em desenvolvimento

**1. Backend** (API em `http://127.0.0.1:8010`, documentação em `/api/docs/`). Passo a passo completo em
[backend/README.md](backend/README.md):

```bash
cd backend
docker compose up -d          # PostgreSQL, Redis e armazenamento de imagens
python manage.py migrate
python manage.py runserver
```

**2. Frontend** (`http://localhost:3000`):

```bash
cd frontend
npm install
npm run dev
```

A API já libera o CORS para `http://localhost:3000` quando `DEBUG=True` (variável `CORS_ALLOWED_ORIGINS` do backend).

## Integração contínua

O workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) roda a cada push na `main` e em todo pull request, com dois
jobs independentes: **backend** (ruff, migrations, `check --deploy`, testes com PostgreSQL 17 e build da imagem Docker) e
**frontend** (eslint e `next build`).
