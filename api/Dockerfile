# Публичный API (api.main): сценарий досье; формулу расчёта не содержит.
# Контекст сборки — корень репозитория; состав контекста задаёт корневой .dockerignore.
FROM python:3.13.18-slim-trixie@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Непривилегированный пользователь; каталог журнала принадлежит ему, и пустой
# named volume при первом монтировании наследует этого владельца.
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home \
        --home-dir /nonexistent --shell /usr/sbin/nologin app \
    && mkdir -p /var/log/domdossier \
    && chown app:app /var/log/domdossier

COPY api ./api
COPY contract ./contract
COPY core ./core
COPY dossier ./dossier
COPY sources ./sources
COPY dataset/utility-rating-dataset.schema.json ./dataset/utility-rating-dataset.schema.json

USER app

EXPOSE 8000

# Graceful shutdown короче stop_grace_period (30s) в compose.yaml.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "25"]
