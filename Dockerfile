FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations

RUN python -m pip install --no-cache-dir . \
    && addgroup --system promptchived \
    && adduser --system --ingroup promptchived --home /app promptchived \
    && mkdir -p /app/.models \
    && chown -R promptchived:promptchived /app

USER promptchived

EXPOSE 8765

CMD ["promptchived", "serve"]
