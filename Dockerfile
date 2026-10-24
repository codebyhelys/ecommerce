FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# dependências primeiro: a camada só é refeita quando o requirements.txt muda
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# o collectstatic só carrega as settings (não conecta ao banco): valores falsos, que não ficam no ambiente em execução
RUN SECRET_KEY=build-only DEBUG=False DB_NAME=build DB_USER=build DB_PASSWORD=build python manage.py collectstatic --noinput

# não roda como root; MEDIA_ROOT (uploads) precisa ser gravável e deve ser um volume em produção
RUN useradd --system --create-home app && mkdir -p /app/media && chown app /app/media
USER app

EXPOSE 8000
# migrações NÃO rodam aqui: execute `python manage.py migrate` como passo de release (veja o README)
# workers, threads e timeouts vêm do gunicorn.conf.py (ajustáveis por WEB_CONCURRENCY e GUNICORN_THREADS)
CMD ["gunicorn", "core.wsgi:application"]
