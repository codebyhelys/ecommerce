# E-commerce — Backend

API REST de um e-commerce: catálogo, contas, carrinho, pedidos e pagamentos.
Django 6 + Django REST Framework + PostgreSQL (Docker).

## Funcionalidades

| App | O que faz |
|---|---|
| `products` | Catálogo com categorias, busca, filtros, ordenação e paginação |
| `accounts` | Usuário com login por e-mail, cadastro, login/logout (tokens Knox) e perfil |
| `cart` | Carrinho por usuário, com validação de estoque |
| `orders` | Checkout a partir do carrinho, preço congelado, baixa de estoque e cancelamento |
| `payments` | Pagamento por pedido, webhook assinado e idempotente |

## Requisitos

- Python 3.12 ou superior (desenvolvido com 3.14)
- Docker Desktop (para o PostgreSQL)
- Git

## Como rodar

```bash
git clone <url-do-repositorio>
cd backend
```

**1. Ambiente virtual e dependências**

```bash
python -m venv .venv
```

Ative: `.venv\Scripts\Activate.ps1` (Windows PowerShell) ou `source .venv/bin/activate` (Linux/macOS).

```bash
pip install -r requirements-dev.txt
```

**2. Variáveis de ambiente**

```bash
cp .env.example .env
```

No PowerShell: `Copy-Item .env.example .env`. Edite o `.env` e troque `SECRET_KEY`, `DB_PASSWORD` e
`PAYMENT_WEBHOOK_SECRET`. Para gerar uma chave:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

**3. Banco de dados (PostgreSQL em Docker)**

```bash
docker compose up -d
```

O container usa `DB_NAME`, `DB_USER`, `DB_PASSWORD` e `DB_PORT` do `.env`. Se a porta 5432 estiver ocupada,
mude `DB_PORT` no `.env` antes de subir.

**4. Migrations e superusuário**

```bash
python manage.py migrate
python manage.py createsuperuser
```

O login é por **e-mail**.

**5. Servidor de desenvolvimento**

```bash
python manage.py runserver
```

Sobe em `http://127.0.0.1:8010` (porta definida por `DEV_SERVER_PORT`). Admin em `/admin/`.

## Testes

```bash
python manage.py test
```

Exigem o banco no ar. Durante o `manage.py test` o hash de senha é trocado por um mais rápido (a suíte leva
a metade do tempo); fora dos testes continua o padrão seguro do Django. Os testes de concorrência (última unidade de estoque, webhook duplicado) usam
threads e travas de linha, então **só fazem sentido em PostgreSQL**. Não rode duas execuções ao mesmo tempo:
elas disputam o mesmo banco de teste.

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `SECRET_KEY` | — (obrigatória) | Chave secreta do Django |
| `DEBUG` | `False` | `True` apenas em desenvolvimento |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Hosts permitidos, separados por vírgula |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | — (obrigatórias) | Credenciais do PostgreSQL |
| `DB_HOST` | `127.0.0.1` | Host do banco (use IPv4: `localhost` pode resolver para `::1` e travar) |
| `DB_CONNECT_TIMEOUT` | `10` | Segundos até desistir de conectar ao banco |
| `DB_PORT` | `5432` | Porta publicada pelo container |
| `DEV_SERVER_PORT` | `8010` | Porta do `runserver` |
| `PAYMENT_GATEWAY` | `fake` com `DEBUG=True`; vazio caso contrário | Provedor de pagamento. Em produção é obrigatório definir; `check --deploy` recusa `fake` |
| `PAYMENT_WEBHOOK_SECRET` | vazio | Segredo da assinatura dos webhooks (vazio rejeita tudo) |
| `ORDER_PENDING_TTL_MINUTES` | `60` | Idade a partir da qual um pedido não pago é cancelado |
| `PAYMENT_WINDOW_MINUTES` | `30` | Enquanto houver pagamento criado há menos que isso, o pedido não expira |
| `PAYMENT_STALE_MINUTES` | `10` | Pagamento que nunca chegou ao provedor é liberado depois disso |
| `THROTTLE_ANON_RATE` / `THROTTLE_USER_RATE` | `100/min` / `300/min` | Limite global de requisições (anônimo por IP; logado por usuário) |
| `LOG_LEVEL` | `INFO` | Nível dos logs no console |
| `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | `True` se `DEBUG=False` | Segurança de produção |
| `SECURE_HSTS_SECONDS` | `3600` se `DEBUG=False` | HSTS (aumente gradualmente em produção) |
| `BEHIND_PROXY` | `False` | `True` atrás de proxy/balanceador que envia `X-Forwarded-Proto` |

## API

Autenticação: header `Authorization: Token <token>`, obtido em `/api/auth/login/`.
Listagens são paginadas (12 por página, `?page=2`).

| Rota | Métodos | Acesso |
|---|---|---|
| `/api/products/`, `/api/products/<slug>/` | GET público; POST/PUT/PATCH/DELETE staff | `?category=`, `?min_price=`, `?max_price=`, `?search=`, `?ordering=` |
| `/api/categories/`, `/api/categories/<slug>/` | GET público; escrita staff | Apagar categoria com produtos retorna 409 |
| `/api/auth/register/` | POST | Público |
| `/api/auth/login/` | POST | Público (`{"email", "password"}`) |
| `/api/auth/logout/`, `/api/auth/logoutall/` | POST | Logado |
| `/api/auth/me/` | GET, PATCH | Logado |
| `/api/cart/` | GET, DELETE | Logado |
| `/api/cart/items/` | POST | Adiciona (soma se já existir) |
| `/api/cart/items/<slug>/` | PATCH, DELETE | Altera a quantidade / remove |
| `/api/orders/` | POST, GET | Finaliza o carrinho (envia só o endereço) / lista os seus |
| `/api/orders/<id>/` | GET | Detalhe (pedido de outro usuário retorna 404) |
| `/api/orders/<id>/cancel/` | POST | Cancela pedido pendente e devolve o estoque |
| `/api/payments/` | POST, GET | Inicia pagamento `{"order", "method"}` / lista |
| `/api/payments/<id>/` | GET | Consulta o status |
| `/api/payments/webhooks/<provider>/` | POST | Chamado pelo provedor, protegido por assinatura. Responde `404 unmatched` se o pagamento ainda não existe (o provedor reenvia) |

## Fluxo de compra

1. Cadastro e login → token.
2. `POST /api/cart/items/` para cada produto.
3. `POST /api/orders/` com o endereço de entrega: valida estoque, congela preços, baixa o estoque e esvazia o carrinho.
4. `POST /api/payments/` com o pedido e o método (ex.: `pix`).
5. O provedor chama o webhook; o pagamento é aprovado e o pedido passa a `paid`.

## Decisões de arquitetura

- **Usuário customizado** com e-mail único sem diferenciar maiúsculas (constraint no banco).
- **Regras de negócio em `services.py`**, fora das views, para serem reaproveitadas (o checkout usa o carrinho).
- **Preço e nome congelados** no item do pedido.
- **Estoque protegido por `select_for_update`**: duas compras da última unidade, ou o mesmo carrinho finalizado
  duas vezes, resultam em um único pedido.
- **Um pagamento ativo por pedido**, garantido por constraint parcial no banco.
- **Webhooks**: assinatura verificada antes de tudo, eventos registrados com unicidade (idempotência),
  valor conferido e transições só para frente. Pagamento aprovado depois do cancelamento é marcado `needs_refund`.
- **Exclusão lógica** de produtos (`is_active`), para preservar o histórico de pedidos.
- **Provedor de pagamento plugável** (`payments/gateways.py`); `fake` é só para desenvolvimento.
- **Webhook sem pagamento correspondente não é gravado**: o provedor reenvia e o evento é processado depois.
- **Pedidos não pagos expiram** e devolvem o estoque (`expire_pending_orders`).
- **Status do pedido só muda por regras**: no admin é somente leitura, com ações de enviar, entregar e cancelar.
- **Edição de produto não sobrescreve o estoque** baixado por um checkout simultâneo.

## Tarefas agendadas

Pedidos pendentes seguram estoque. Agende o comando abaixo para rodar a cada poucos minutos
(cron no Linux, Agendador de Tarefas no Windows):

```bash
python manage.py expire_pending_orders
```

Ele cancela pedidos não pagos com mais de `ORDER_PENDING_TTL_MINUTES` (devolvendo o estoque) e libera
pagamentos que nunca chegaram ao provedor. Pedidos com um pagamento criado há menos de
`PAYMENT_WINDOW_MINUTES` são preservados. Configure o prazo do Pix no provedor para ser menor que a soma dos dois.

Exemplos de agendamento a cada 5 minutos:

```bash
*/5 * * * * cd /caminho/backend && .venv/bin/python manage.py expire_pending_orders
```

```powershell
schtasks /Create /SC MINUTE /MO 5 /TN "ecommerce-expire-pending-orders" /TR "C:\caminho\backend\.venv\Scripts\python.exe C:\caminho\backend\manage.py expire_pending_orders"
```

Não agende na sua máquina de desenvolvimento: ele cancelaria pedidos de teste esquecidos. É para o servidor.

## Produção

- `DEBUG=False`, `SECRET_KEY` própria e `ALLOWED_HOSTS` com o domínio.
- `PAYMENT_GATEWAY` com o provedor real (com `fake`, `python manage.py check --deploy` falha).
- Com `DEBUG=False` o redirecionamento para HTTPS e os cookies seguros ficam ligados. Em testes locais ou CI sem HTTPS,
  defina `SECURE_SSL_REDIRECT=False`.
- Valide com `python manage.py check --deploy`.

## Privacidade (LGPD)

Para atender a um pedido de exclusão de dados, anonimize a conta:

```bash
python manage.py anonymize_user pessoa@example.com
```

Remove nome e e-mail, desativa a conta, apaga tokens e carrinho e libera o e-mail para um novo cadastro.
O histórico de pedidos é mantido (obrigação fiscal), com o endereço de entrega que foi copiado para cada pedido.
Contas de equipe (`is_staff`) não podem ser anonimizadas por esse comando.

## Qualidade

```bash
ruff check .            # lint
ruff format .           # formatação
python manage.py test   # testes
```

O GitHub Actions (`.github/workflows/ci.yml`) roda tudo isso, mais `makemigrations --check` e
`check --deploy`, a cada push e pull request, com PostgreSQL 17 e `DEBUG=False`.

## Estrutura

```
backend/
├── core/        # settings, urls
├── products/    # catálogo
├── accounts/    # usuários e autenticação
├── cart/        # carrinho
├── orders/      # pedidos
├── payments/    # pagamentos e webhooks
├── docs/        # planos e decisões (ex.: Mercado Pago)
├── .github/     # CI
├── docker-compose.yml
└── manage.py
```

## Problemas comuns

| Sintoma | Causa e solução |
|---|---|
| Comandos travam ou dão `connection timeout` | Banco fora do ar. Abra o Docker Desktop e rode `docker compose up -d`. |
| `port is already allocated` | Porta ocupada por outro container. Mude `DB_PORT` no `.env`. |
| `database "test_..." is being accessed by other users` | Outra execução de testes está rodando. Espere terminar. |
| `InconsistentMigrationHistory` | `AUTH_USER_MODEL` foi alterado depois do primeiro `migrate`. Em desenvolvimento, `docker compose down -v` e suba de novo (apaga os dados). |
| `UndefinedValueError: SECRET_KEY` | Falta o `.env`. Copie o `.env.example`. |
| Comandos esperam muito e dão `connection timeout`, mas o container está no ar | `DB_HOST=localhost` resolvendo para IPv6. Use `DB_HOST=127.0.0.1`. |

## Roadmap

- Adaptador do Mercado Pago (Pix e cartão): plano e pendências em [docs/mercadopago.md](docs/mercadopago.md).
- Modelo `Address` e cálculo de frete.
- Cupons de desconto e avaliações de produtos.
- Verificação de e-mail e recuperação de senha.
- Documentação OpenAPI.
