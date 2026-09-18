FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# libs exigidas pelo opencv (img2table/rapidocr)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"

# Dependências primeiro (melhor cache de camadas)
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY input_arquivos ./input_arquivos
COPY main.py ./
RUN uv sync --frozen --no-dev

RUN mkdir -p /app/data
ENV HOST=0.0.0.0 PORT=8004 RELOAD=false
EXPOSE 8004
CMD ["uvicorn", "input_arquivos.main:app", "--host", "0.0.0.0", "--port", "8004", "--proxy-headers", "--forwarded-allow-ips", "*"]
