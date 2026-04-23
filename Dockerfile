FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

FROM base AS deps
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    playwright install chromium --with-deps

FROM deps AS runtime
COPY . .

CMD ["python", "-m", "src.scheduler"]
