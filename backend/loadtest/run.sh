#!/usr/bin/env bash
# Uso (a partir da pasta backend):  loadtest/run.sh browse.js [-e STAGES=20:30s,100:1m,0:10s] [-e PRODUCT=produto-limitado]
# O k6 roda dentro da rede do Docker e fala direto com o container load-web (sem a camada de portas do Windows).
# --no-deps: não recria o load-web (senão o experimento de LOAD_WEB_CONCURRENCY seria desfeito a cada execução).
export MSYS_NO_PATHCONV=1  # impede o Git Bash de converter /scripts em C:/Program Files/Git/scripts
script="$1"; shift
docker compose --profile loadtest run --rm --no-deps -T k6 run --quiet "$@" "/scripts/$script"
