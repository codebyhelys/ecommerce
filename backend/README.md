# E-commerce — Backend

API REST de um e-commerce: catálogo, contas, carrinho, cupons, frete, pedidos, pagamentos e avaliações.
Django 6 + Django REST Framework + PostgreSQL (Docker).

## Funcionalidades

| App | O que faz |
|---|---|
| `products` | Catálogo com categorias, busca, filtros, ordenação, paginação e imagens |
| `accounts` | Login por e-mail, cadastro, tokens Knox, perfil, endereços salvos e recuperação/troca de senha |
| `cart` | Carrinho por usuário, com validação de estoque e estimativa de frete |
| `coupons` | Cupons (percentual ou valor fixo) com validade, mínimo, limite total e por usuário |
| `orders` | Checkout, preço/frete/desconto congelados, estoque, cancelamento, rastreio e e-mails do pedido |
| `payments` | Pagamento por pedido, webhook assinado e idempotente, controle de estornos |
| `reviews` | Avaliações de 1 a 5 só de quem comprou, com nota média no produto |

## Requisitos

- Python 3.12 ou superior (desenvolvido com 3.14)
- Docker Desktop (para o PostgreSQL)
- Git

## Como rodar

```bash
git clone https://github.com/codebyhelys/ecommerce.git
cd ecommerce/backend
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

O mesmo comando sobe o **Redis** (cache e contadores do throttling), com `REDIS_PORT` e `REDIS_PASSWORD` do `.env`.
Para o Django usá-lo, defina `REDIS_URL` (ex.: `redis://:SENHA@127.0.0.1:16379/0`). Sem `REDIS_URL` o cache fica
em memória, o que basta em desenvolvimento, mas **o limite de requisições deixa de valer entre workers**: em produção
`REDIS_URL` é obrigatório. A suíte de testes sempre usa o cache em memória.

E o **armazenamento de objetos** para as imagens (SeaweedFS, compatível com S3): o serviço `storage` sobe o servidor e o
`storage-setup` cria o bucket e termina. Usa `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_NAME` e `STORAGE_PORT` do `.env`.
Com `S3_BUCKET_NAME` definido, o Django grava e lê as imagens ali (veja *Armazenamento de arquivos*).

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
| `DB_CONN_MAX_AGE` | `60` | Segundos que cada conexão com o banco é reaproveitada (`0` abre uma por requisição) |
| `WEB_CONCURRENCY` | `3` | Processos (workers) do gunicorn no container |
| `GUNICORN_THREADS` | `4` | Threads por worker. Requisições simultâneas = workers x threads |
| `GUNICORN_MAX_REQUESTS` | `0` (desligado) | Recicla cada worker após N requisições. Só ligue atrás de um proxy que repita requisições: sem ele, cada reinício derruba conexões |
| `DB_PORT` | `5432` | Porta publicada pelo container |
| `REDIS_URL` | vazio (cache em memória) | Cache compartilhado e throttling. `rediss://` para TLS |
| `REDIS_PORT`, `REDIS_PASSWORD` | `6379`, — | Porta e senha do container Redis do `docker-compose.yml` |
| `CELERY_BROKER_URL` | vazio (tarefas rodam na hora, sem worker) | Broker das tarefas em segundo plano. Use o Redis em **outro banco lógico** que o cache (ex.: `/1`) |
| `DEV_SERVER_PORT` | `8010` | Porta do `runserver` |
| `PAYMENT_GATEWAY` | `fake` com `DEBUG=True`; vazio caso contrário | Provedor de pagamento. Em produção é obrigatório definir; `check --deploy` recusa `fake` |
| `PAYMENT_WEBHOOK_SECRET` | vazio | Segredo da assinatura dos webhooks (vazio rejeita tudo) |
| `ORDER_PENDING_TTL_MINUTES` | `60` | Idade a partir da qual um pedido não pago é cancelado |
| `PAYMENT_WINDOW_MINUTES` | `30` | Enquanto houver pagamento criado há menos que isso, o pedido não expira |
| `PAYMENT_STALE_MINUTES` | `10` | Pagamento que nunca chegou ao provedor é liberado depois disso |
| `THROTTLE_ANON_RATE` / `THROTTLE_USER_RATE` | `100/min` / `300/min` | Limite global de requisições (anônimo por IP; logado por usuário) |
| `SHIPPING_FLAT_RATE` | `19.90` | Frete fixo por pedido |
| `SHIPPING_FREE_ABOVE` | `299.00` | Frete grátis a partir deste valor dos itens (já com desconto); vazio desativa |
| `EMAIL_BACKEND` | console | Em produção use `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | `localhost`, `25`, vazio, vazio, `False` | SMTP (e-mails de pedido e de redefinição de senha) |
| `DEFAULT_FROM_EMAIL` | `Loja <nao-responda@loja.local>` | Remetente |
| `FRONTEND_URL` | `http://localhost:3000` | Base do link de redefinição de senha enviado por e-mail |
| `CORS_ALLOWED_ORIGINS` | localhost:3000 com `DEBUG=True`; vazio caso contrário | Origens do front-end autorizadas a chamar `/api/`, separadas por vírgula |
| `MEDIA_ROOT` | `./media` | Pasta dos uploads (imagens de produto) |
| `PRODUCT_IMAGE_MAX_BYTES` | `5242880` | Tamanho máximo de cada imagem (5 MB) |
| `S3_BUCKET_NAME` | vazio (disco local) | Liga o armazenamento de objetos |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | — (obrigatórias com bucket) | Credenciais. Em produção use uma chave só com acesso a esse bucket |
| `S3_ENDPOINT_URL` | vazio (AWS S3) | Endereço do servidor S3-compatível (R2, SeaweedFS...) |
| `S3_REGION` | `us-east-1` | Região |
| `S3_ADDRESSING_STYLE` | `virtual` | `path` em servidores locais |
| `S3_PUBLIC_DOMAIN`, `S3_PUBLIC_PROTOCOL` | vazio, `https:` | Endereço público das imagens (CDN, ou servidor + `/bucket`). Em desenvolvimento use `http:` |
| `STORAGE_PORT` | `8333` | Porta do servidor S3 de desenvolvimento no `docker-compose.yml` |
| `LOG_LEVEL` | `INFO` | Nível dos logs no console |
| `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | `True` se `DEBUG=False` | Segurança de produção |
| `SECURE_HSTS_SECONDS` | `3600` se `DEBUG=False` | HSTS (aumente gradualmente em produção) |
| `BEHIND_PROXY` | `False` | `True` atrás de proxy/balanceador que envia `X-Forwarded-Proto` |

## API

Autenticação: header `Authorization: Token <token>`, obtido em `/api/auth/login/`.
Listagens são paginadas (12 por página, `?page=2`).

Documentação interativa (OpenAPI/Swagger): **`/api/docs/`**; o esquema bruto está em `/api/schema/`.
A página usa assets de CDN. A geração do esquema é validada nos testes: uma view nova sem anotação quebra a suíte.

| Rota | Métodos | Acesso |
|---|---|---|
| `/api/products/`, `/api/products/<slug>/` | GET público; POST/PUT/PATCH/DELETE staff | `?category=`, `?min_price=`, `?max_price=`, `?search=`, `?ordering=`. Traz `images`, `rating_average` e `reviews_count` |
| `/api/products/<slug>/images/` | POST (staff, `multipart/form-data`: `image`, `alt_text`, `position`) | JPEG, PNG ou WEBP, até 5 MB, no máximo 8 por produto |
| `/api/products/<slug>/images/<id>/` | DELETE (staff) | Remove a linha e o arquivo |
| `/api/products/<slug>/reviews/` | GET público; POST logado | Só quem tem pedido pago/enviado/entregue do produto avalia; uma avaliação por usuário (409 se repetir) |
| `/api/products/<slug>/reviews/<id>/` | GET; PATCH (autor); DELETE (autor ou staff) | |
| `/api/categories/`, `/api/categories/<slug>/` | GET público; escrita staff | Apagar categoria com produtos retorna 409 |
| `/api/auth/register/` | POST | Público |
| `/api/auth/login/` | POST | Público (`{"email", "password"}`) |
| `/api/auth/logout/`, `/api/auth/logoutall/` | POST | Logado |
| `/api/auth/me/` | GET, PATCH | Logado |
| `/api/auth/password/change/` | POST | Logado; exige a senha atual e encerra as outras sessões |
| `/api/auth/password/reset/` | POST | Público; envia o link por e-mail (resposta igual exista a conta ou não) |
| `/api/auth/password/reset/confirm/` | POST | Público; `{uid, token, new_password}` |
| `/api/addresses/`, `/api/addresses/<id>/` | CRUD | Logado; até 10 por conta, um padrão |
| `/api/coupons/validate/` | POST | Logado; `{"code"}` pré-visualiza o desconto sobre o carrinho (limitado a 20/min) |
| `/api/cart/` | GET, DELETE | Logado; mostra `shipping_estimate` e `estimated_total` |
| `/api/cart/items/` | POST | Adiciona (soma se já existir) |
| `/api/cart/items/<slug>/` | PATCH, DELETE | Altera a quantidade / remove |
| `/api/orders/` | POST, GET | Finaliza o carrinho: `address` (id de um endereço salvo) **ou** os campos `shipping_*`; opcional `coupon`. Lista os seus |
| `/api/orders/<id>/` | GET | Detalhe (pedido de outro usuário retorna 404) |
| `/api/orders/<id>/cancel/` | POST | Cancela pedido pendente e devolve o estoque |
| `/api/payments/` | POST, GET | Inicia pagamento `{"order", "method"}` / lista |
| `/api/payments/<id>/` | GET | Consulta o status |
| `/api/health/` | GET | Sonda do balanceador: 200 se o banco responde, 503 se não |
| `/api/payments/webhooks/<provider>/` | POST | Chamado pelo provedor, protegido por assinatura. Responde `404 unmatched` se o pagamento ainda não existe (o provedor reenvia) |

## Fluxo de compra

1. Cadastro e login → token.
2. `POST /api/cart/items/` para cada produto.
3. (Opcional) `POST /api/coupons/validate/` para mostrar o desconto.
4. `POST /api/orders/` com o endereço de entrega e o cupom: valida estoque e cupom, congela preços, frete e desconto,
   baixa o estoque e esvazia o carrinho. O cliente recebe o e-mail de confirmação.
5. `POST /api/payments/` com o pedido e o método (ex.: `pix`).
6. O provedor chama o webhook; o pagamento é aprovado, o pedido passa a `paid` e sai o e-mail de pagamento confirmado.
7. A equipe marca como enviado (com o código de rastreio, editável no admin) e depois como entregue; cada passo avisa o cliente.
8. Quem comprou pode avaliar o produto.

### Cancelamento e estorno

- Pedido **pendente**: o cliente cancela (`POST /api/orders/<id>/cancel/`) ou ele expira; o estoque e o cupom voltam.
- Pedido **pago e não enviado**: só a equipe cancela, no admin (*Cancelar pedidos PAGOS…*). O estoque volta e o pagamento
  fica `needs_refund`. Faça o estorno no painel do provedor e então use, em *Pagamentos*, a ação
  *Registrar estorno JÁ realizado*: o pagamento vira `refunded`. Filtre por `needs_refund` para ver o que está pendente.
- Pagamento que chega **depois** do cancelamento também cai em `needs_refund` (o pedido não é reaberto).

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
- **Total = itens − desconto + frete**, tudo congelado no pedido; o cupom é travado (`select_for_update`) para respeitar os limites de uso.
- **E-mails só depois do commit** (`transaction.on_commit`) e nunca derrubam a operação: falha de SMTP é registrada no log.
- **Uploads com nome aleatório**, formato e tamanho validados; o arquivo some junto com a linha (após o commit).
- **Avaliações**: nota média e contagem calculadas na própria consulta da listagem (sem N+1).
- **Anonimização** (LGPD) apaga também endereços e avaliações.
- **E-mails em segundo plano** (Celery): a requisição só enfileira. Falha de SMTP é repetida com espera crescente (até 5 vezes);
  se o broker estiver fora do ar, o e-mail é enviado na hora. A redefinição de senha também é enfileirada, então a resposta
  demora o mesmo exista a conta ou não.
- **Arquivos fora do disco do servidor**: as imagens vão para um armazenamento S3-compatível, e várias instâncias compartilham o mesmo bucket.

## Tarefas em segundo plano (Celery)

E-mails (pedido e redefinição de senha) e a expiração de pedidos rodam em um **worker** separado, com o Redis como broker.
Sem `CELERY_BROKER_URL` (padrão em desenvolvimento e nos testes) as tarefas rodam na hora, dentro da requisição, e não
é preciso worker.

Para usar a fila, defina `CELERY_BROKER_URL` no `.env` (mesmo Redis do cache, banco `/1`) e rode, em terminais separados:

```bash
celery -A core worker -l info -P solo     # -P solo é necessário no Windows; no Linux omita
celery -A core beat -l info               # agendador: só no servidor, e UMA única instância
```

O `beat` dispara o `expire_pending_orders` a cada 5 minutos (`CELERY_BEAT_SCHEDULE`). Não o rode na máquina de desenvolvimento.
Se o worker estiver parado, as tarefas esperam na fila e saem quando ele voltar.

## Tarefas agendadas (sem Celery)

Pedidos pendentes seguram estoque. Sem o `beat`, agende o comando abaixo para rodar a cada poucos minutos
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
- Defina `CORS_ALLOWED_ORIGINS` (domínio do front-end), `EMAIL_BACKEND` SMTP e `FRONTEND_URL`.
- **Uploads**: o Django não serve `/media/` com `DEBUG=False`. Use um bucket S3-compatível (veja *Armazenamento de arquivos*).
  Sem `S3_BUCKET_NAME` as imagens ficam em `MEDIA_ROOT`, que precisa de volume persistente e de um proxy servindo `/media/`.
- **Redis**: `REDIS_URL` e `CELERY_BROKER_URL` são obrigatórios. Sem o primeiro, o limite de requisições vale por processo; sem o
  segundo, os e-mails atrasam a resposta.

### Docker

O `Dockerfile` gera uma imagem com gunicorn (3 workers x 4 threads, em `gunicorn.conf.py`), estáticos servidos por
WhiteNoise e usuário sem privilégios.

**Dimensionamento:** cada thread mantém uma conexão com o PostgreSQL, então um container usa até
`WEB_CONCURRENCY x GUNICORN_THREADS` conexões (12 por padrão). Some todos os containers e compare com o
`max_connections` do banco (100 por padrão); passando disso, coloque um PgBouncer na frente.

```bash
docker build -t ecommerce-backend .
docker run --env-file .env -e DEBUG=False -e DB_HOST=<host-do-banco> -p 8000:8000 -v media:/app/media ecommerce-backend
```

As migrações **não** rodam sozinhas ao subir o container. Execute-as como passo de release, uma vez por versão:

```bash
docker run --rm --env-file .env -e DEBUG=False -e DB_HOST=<host-do-banco> ecommerce-backend python manage.py migrate
```

O **worker** e o **beat** usam a mesma imagem, com outro comando:

```bash
docker run -d --env-file .env -e DEBUG=False ecommerce-backend celery -A core worker -l info --concurrency 4
docker run -d --env-file .env -e DEBUG=False ecommerce-backend celery -A core beat -l info --schedule /tmp/celerybeat-schedule
```

Rode **uma só** instância do `beat` (duas disparariam cada tarefa duas vezes); workers podem ser quantos precisar.

Atrás de HTTPS use `BEHIND_PROXY=True`. Configure a sonda de saúde do balanceador em `GET /api/health/` (não é redirecionada
para HTTPS).

## Armazenamento de arquivos

As imagens de produto são públicas e têm nome aleatório, então são servidas por URL direta (sem assinatura), com
`Cache-Control` de um ano. Em desenvolvimento, o `docker-compose.yml` sobe um servidor S3-compatível (**SeaweedFS**; o MinIO
deixou de publicar imagens oficiais). Em produção troque só as variáveis `S3_*`:

- **AWS S3**: bucket com leitura pública do prefixo `products/`, uma chave de acesso só para esse bucket e, se quiser CDN,
  `S3_PUBLIC_DOMAIN` com o domínio dele.
- **Cloudflare R2 ou outro compatível**: informe `S3_ENDPOINT_URL` e `S3_PUBLIC_DOMAIN`.

O bucket não deve permitir listagem nem escrita anônimas (em desenvolvimento só há leitura anônima).
Trocar de storage não migra as imagens existentes: copie os arquivos de `MEDIA_ROOT` para o bucket mantendo os nomes.

## Privacidade (LGPD)

Para atender a um pedido de exclusão de dados, anonimize a conta:

```bash
python manage.py anonymize_user pessoa@example.com
```

Remove nome e e-mail, desativa a conta, apaga tokens, carrinho, endereços e avaliações e libera o e-mail para um novo cadastro.
O histórico de pedidos é mantido (obrigação fiscal), com o endereço de entrega que foi copiado para cada pedido.
Contas de equipe (`is_staff`) não podem ser anonimizadas por esse comando.

## Qualidade

```bash
ruff check .            # lint
ruff format .           # formatação
python manage.py test   # testes
```

O GitHub Actions (`../.github/workflows/ci.yml`, na raiz do repositório) roda tudo isso, mais `makemigrations --check` e
`check --deploy` e o build da imagem Docker, a cada push e pull request, com PostgreSQL 17 e `DEBUG=False`.

## Estrutura

```
backend/
├── core/        # settings, urls
├── products/    # catálogo
├── accounts/    # usuários e autenticação
├── cart/        # carrinho
├── coupons/     # cupons de desconto
├── orders/      # pedidos, frete e e-mails
├── payments/    # pagamentos, webhooks e estornos
├── reviews/     # avaliações
├── docs/        # planos e decisões (ex.: Mercado Pago)
├── Dockerfile
├── docker-compose.yml   # só o PostgreSQL de desenvolvimento
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
- Frete por CEP/transportadora (hoje é valor fixo com faixa de frete grátis).
- Verificação de e-mail no cadastro.
- Devolução de pedidos já enviados e estorno automático pelo provedor.
- Monitoramento das filas (Flower ou métricas do Redis) e alarmes para e-mails que esgotaram as tentativas.
