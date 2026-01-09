FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md /app/
COPY certman /app/certman
COPY main.py /app/main.py

RUN uv sync --frozen

ENTRYPOINT ["uv", "run", "certman"]
