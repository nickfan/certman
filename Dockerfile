FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://dl.k8s.io/release/v1.34.1/bin/linux/amd64/kubectl -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md /app/
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY certman /app/certman
COPY main.py /app/main.py

RUN uv sync --frozen --no-dev

ENTRYPOINT ["uv", "run", "certman"]
