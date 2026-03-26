FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir uv==0.11.1

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY . .

RUN mkdir -p /data

EXPOSE 8000

ENTRYPOINT ["uv", "run", "python", "main.py"]
CMD ["serve", "--config", "/data/config.json", "--non-interactive", "--host", "0.0.0.0"]
