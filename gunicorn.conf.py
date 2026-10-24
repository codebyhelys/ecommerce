"""Configuração do gunicorn (lida automaticamente da pasta atual). Tudo ajustável por variável de ambiente."""

import os

bind = "0.0.0.0:8000"

# processos x threads = requisições simultâneas por container. Cada thread usa UMA conexão com o banco
# (CONN_MAX_AGE), então 3 x 4 = até 12 conexões por container: some todos os containers e compare com o
# max_connections do PostgreSQL (100 por padrão). Passando disso, coloque um PgBouncer na frente do banco.
workers = int(os.environ.get("WEB_CONCURRENCY", 3))
threads = int(os.environ.get("GUNICORN_THREADS", 4))
worker_class = "gthread"

timeout = 30  # uma requisição presa por mais que isso mata o worker em vez de travá-lo para sempre
graceful_timeout = 30
# Reciclar workers (GUNICORN_MAX_REQUESTS > 0) contém vazamentos de memória, mas, sem um proxy na frente, cada reinício
# derruba as conexões abertas naquele instante (medido: ~0,1-0,2% de erros sob carga). Por isso vem DESLIGADO (0):
# ligue só atrás de um proxy (nginx) que repita a requisição, ou se o monitoramento mostrar a memória crescendo.
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", 0))
max_requests_jitter = max_requests // 10  # variação, para os workers não reiniciarem todos juntos

accesslog = "-"
