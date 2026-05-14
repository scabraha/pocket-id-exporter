# syntax=docker/dockerfile:1.24

FROM python:3.14-alpine AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.14-alpine
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN addgroup -S exporter && adduser -S -G exporter exporter
WORKDIR /app
COPY --from=builder /install /usr/local
COPY pocket_id_exporter ./pocket_id_exporter
USER exporter
EXPOSE 9100
ENTRYPOINT ["python", "-m", "pocket_id_exporter"]
