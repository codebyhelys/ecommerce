# Teste de carga

Mede quanto a API aguenta e **onde ela cede primeiro**. Usa o [k6](https://k6.io) dentro do Docker, contra uma cópia
da API em modo de produção (gunicorn, `DEBUG=False`), com banco, cache e fila **próprios** (`ecommerce_load`, Redis
`/2` e `/3`). Nada aqui toca no banco de desenvolvimento.

Dentro do ambiente de teste: limites de requisição elevados (senão tudo vira 429), e-mail descartado e gateway `fake`.

## Passo a passo (a partir da pasta `backend`)

```bash
# 1. banco de carga (uma vez)
docker compose up -d db redis
docker exec ecommerce_db sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "create database ecommerce_load"'
DB_NAME=ecommerce_load python manage.py migrate

# 2. dados: 5000 produtos, 400 usuários, 24 mil avaliações, um token por usuário (loadtest/tokens.json)
DB_NAME=ecommerce_load python loadtest/seed.py

# 3. sobe a API de teste e o worker
docker compose --profile loadtest up -d --build load-web load-worker

# 4. roda um cenário
loadtest/run.sh browse.js
loadtest/run.sh shop.js
loadtest/run.sh hot.js -e PRODUCT=produto-quente
loadtest/run.sh hot.js -e PRODUCT=produto-limitado
```

No PowerShell, rode os `loadtest/run.sh` pelo Git Bash (ou copie o comando `docker compose --profile loadtest run --rm -T k6 run --quiet /scripts/<cenário>.js`).

Para ajustar a carga: `-e STAGES=20:30s,100:1m,0:10s` (alvo de usuários virtuais e duração de cada degrau).
Para experimentar o tamanho do servidor: `LOAD_WEB_CONCURRENCY=8 docker compose --profile loadtest up -d --force-recreate load-web`
(confira com `docker exec ecommerce_load_web env | grep WEB_CONC`; o `run.sh` não recria o container).

Para ver CPU e memória enquanto o teste roda, em outro terminal: `loadtest/sample.sh` (Ctrl+C para parar).

## Cenários

| Arquivo | O que simula |
|---|---|
| `browse.js` | Navegação anônima: listagem, categoria, busca, faixa de preço e detalhe |
| `shop.js` | Compra completa logada: carrinho, pedido e início do pagamento |
| `hot.js` | Todos comprando o **mesmo** produto. Com `produto-limitado` (300 unidades) prova que não se vende a mais |

Depois do `hot.js` com `produto-limitado`, confira no banco que o estoque zerou e que as unidades vendidas somam 300:

```bash
docker exec ecommerce_db sh -c 'psql -U "$POSTGRES_USER" -d ecommerce_load -c "select stock from products_product where slug='"'"'produto-limitado'"'"'"'
```

## Recomeçar do zero

```bash
docker compose --profile loadtest stop load-web load-worker
docker exec ecommerce_db sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "drop database ecommerce_load" -c "create database ecommerce_load"'
```

e repita os passos 1 e 2. (O `produto-limitado` só vende 300 unidades por banco populado.)

## Como ler o resultado

- **p95**: 95% das respostas foram mais rápidas que isso. É o número que o usuário sente.
- **http_req_failed**: erros. Em `hot.js` os 400 de "sem estoque" contam como falha e são esperados; vale o check `resposta esperada`.
- Compare o `docker stats` com o resultado: o container que chega perto de `100% x núcleos` é o gargalo.

Os números valem para a máquina onde rodou (Docker Desktop, 12 CPUs lógicas, 8 GB) com o k6 competindo pelos mesmos
núcleos. Use-os para **comparar antes e depois** de uma mudança, não como capacidade de produção.

## Medições (antes e depois das otimizações)

Máquina: Docker Desktop com 12 CPUs lógicas e 8 GB, k6 no mesmo computador. "3 workers" e "8 workers" são do gunicorn.

| Cenário | Antes (3 workers) | Depois (8 workers) |
|---|---|---|
| `browse.js` até 600 usuários | ~91 req/s, p95 **4,9 s**; Postgres a ~400% de CPU | ~165 req/s, p95 **1,0 s**; Postgres a ~300% |
| `shop.js` até 200 usuários | ~97 req/s, pedido p95 **1,6 s**, 0,16% de erro | ~168 req/s, pedido p95 **179 ms**, 0% de erro |
| `shop.js` até 400 usuários | não medido | **332 req/s (~68 compras/s)**, pedido p95 1,2 s, 0% de erro; API a ~650% (saturada) |
| `hot.js` `produto-quente` | ~45 compras/s, p95 7 s, 2937 iterações descartadas | ~69 compras/s, p95 3,9 s, 637 descartadas |
| `hot.js` `produto-limitado` | **300 vendidas, estoque 0, nada a mais** | **300 vendidas, estoque 0, nada a mais** (p95 124 ms) |

Só a correção da listagem (sem mexer nos workers), no `browse.js`: p95 de 4,9 s para 2,9 s e Postgres de ~400% para ~145%.
A partir daí o limite passou a ser a API (3 workers saturados); aumentar `WEB_CONCURRENCY` fez o resto.

### Causas encontradas e o que foi feito

1. **Listagem cara no banco**: a nota média das avaliações era um `JOIN` + `GROUP BY` que agregava *todos* os produtos
   antes de paginar. Medido direto no Postgres: **26 ms por página contra 2,5 ms** em subconsulta (o `count` da
   paginação: 9 ms contra 1,7 ms). Corrigido em `products/views.py` (`with_review_stats`), com teste que impede a volta
   do `JOIN` no `COUNT`.
2. **Conexões derrubadas (~0,1-0,2%)**: o `max_requests = 1000` do gunicorn reciclava workers a cada ~30 s sob carga e o
   cliente via `EOF`. Agora vem desligado (`GUNICORN_MAX_REQUESTS=0`); some o erro.
3. **Teto da API**: cerca de 30 ms de CPU por requisição autenticada, ~100 req/s por 3 workers. Escala com
   `WEB_CONCURRENCY` (cada worker usa até um núcleo) enquanto o banco aguentar; com 8 workers a API satura em ~650% de CPU
   e o Postgres em ~200-300%.
4. **Redis e Celery folgados**: fila de e-mails sempre vazia.
5. **Correção sob concorrência confirmada**: nenhum estoque vendido a mais, antes e depois.

### Próximos limites conhecidos
- A busca por texto (`icontains`) lê a tabela inteira (~7 ms com 5 mil produtos, cresce linearmente): precisa de índice
  de texto (`pg_trgm`) antes de o catálogo chegar a dezenas de milhares de itens.
- Todos comprando o mesmo produto serializa na trava de linha do estoque (~70 compras/s no mesmo produto).
- Com mais de ~8 workers por container, some as conexões (`workers x threads`) e compare com o `max_connections` do Postgres.
