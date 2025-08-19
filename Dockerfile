FROM python:3.12-alpine AS builder

# Ensure uv copies files rather than hardlinking across layers
ENV UV_LINK_MODE=copy

# See: https://docs.astral.sh/uv/guides/integration/docker/#compiling-bytecode
ENV UV_COMPILE_BYTECODE=1

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy project metadata first for better layer caching
# Include uv.lock if you use one; it's optional
COPY pyproject.toml ./
COPY uv.lock* ./

RUN uv pip install --system --no-cache .

FROM python:3.12-alpine

RUN addgroup -g 1000 -S appuser && \
  adduser -u 1000 -S appuser -G appuser

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY --chown=appuser:appuser ./src .

USER appuser

EXPOSE 8000

CMD ["python", "main.py"]
