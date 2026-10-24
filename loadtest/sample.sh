#!/usr/bin/env bash
# Amostra CPU/memória dos containers a cada 5 s (Ctrl+C ou kill para parar). Saída: linhas "hora nome cpu mem".
while true; do
  docker stats --no-stream --format '{{.Name}} {{.CPUPerc}} {{.MemUsage}}' ecommerce_load_web ecommerce_load_worker ecommerce_db ecommerce_redis | sed "s/^/$(date +%H:%M:%S) /"
  sleep 3
done
