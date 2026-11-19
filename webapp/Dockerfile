# syntax=docker/dockerfile:1

# ---- Frontend build -------------------------------------------------------
FROM node:22-bookworm-slim AS frontend
WORKDIR /app/webapp/frontend
COPY webapp/frontend/package.json webapp/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY webapp/frontend ./
RUN npm run build

# ---- Runtime --------------------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HYDRO_HOST=0.0.0.0 \
    HYDRO_PORT=8080 \
    HYDRO_DATA_DIR=/data

WORKDIR /app

# libgl/libglib are runtime deps of the scientific stack; tesseract is optional.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-ocr.txt webapp/requirements-web.txt ./
RUN pip install -r requirements.txt -r requirements-web.txt -r requirements-ocr.txt

COPY hidrostatik_test ./hidrostatik_test
COPY webapp ./webapp
COPY --from=frontend /app/webapp/frontend/dist ./webapp/frontend/dist

RUN mkdir -p /data && useradd --create-home --uid 10001 hydro \
    && chown -R hydro:hydro /data
USER hydro

VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)"

CMD ["python", "webapp/run_web.py", "--host", "0.0.0.0", "--port", "8080"]
