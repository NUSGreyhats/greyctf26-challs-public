FROM node:24 AS frontend-build

WORKDIR /workspace/src/frontend

COPY src/frontend/package*.json ./
RUN npm ci

COPY src/frontend ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext-base pgbouncer supervisor \
    && groupadd --system pgbouncer \
    && useradd --system --gid pgbouncer --home-dir /nonexistent --shell /usr/sbin/nologin pgbouncer \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY src/backend /app
COPY --from=frontend-build /workspace/src/frontend/dist /app/static
COPY service/backend/pgbouncer.ini.template /etc/pgbouncer/pgbouncer.ini.template
COPY service/backend/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY service/backend/start-app.sh /usr/local/bin/start-backend-app
COPY service/backend/start.sh /usr/local/bin/start-backend-bundle

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir . \
    && chmod +x /usr/local/bin/start-backend-app \
    && chmod +x /usr/local/bin/start-backend-bundle

EXPOSE 8000

CMD ["/usr/local/bin/start-backend-bundle"]
