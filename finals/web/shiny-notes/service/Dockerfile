FROM --platform=linux/amd64 debian:bookworm-slim AS pydeps

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-dev \
        gcc ca-certificates pkg-config \
        default-libmysqlclient-dev \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir \
        Flask==3.0.3 cryptography==43.0.1 mysqlclient==2.2.4 gunicorn==23.0.0 \
        playwright==1.47.0 \
    && find /opt/venv -type d -name __pycache__ -prune -exec rm -rf {} + \
    && find /opt/venv -type f -name '*.pyc' -delete \
    && rm -rf /var/lib/apt/lists/*

FROM --platform=linux/amd64 debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 curl ca-certificates \
        build-essential pkg-config file python3-docutils python3-sphinx \
        libpcre2-dev libedit-dev libjemalloc-dev \
        libmariadb3 \
        default-mysql-server \
        hitch openssl \
        supervisor \
        chromium \
        libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxcomposite1 \
        libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    && curl -fsSL --retry 5 --retry-delay 2 --connect-timeout 20 https://vinyl-cache.org/_downloads/varnish-8.0.1.tgz -o /tmp/varnish.tgz \
    && echo "9f5a22d58acdbeac371a163debcdd36121be5ee4bc84aa187eb7cd0c318fe682  /tmp/varnish.tgz" | sha256sum -c - \
    && tar -xzf /tmp/varnish.tgz -C /tmp \
    && cd /tmp/varnish-8.0.1 \
    && ./configure --prefix=/usr --sysconfdir=/etc --localstatedir=/var \
    && make -j"$(nproc)" \
    && make install \
    && ldconfig \
    && apt-mark manual gcc libc6-dev libpcre2-8-0 libedit2 libjemalloc2 \
    && apt-get purge -y --auto-remove curl build-essential pkg-config file python3-docutils python3-sphinx libpcre2-dev libedit-dev libjemalloc-dev \
    && rm -rf /var/lib/mysql/* \
        /var/lib/apt/lists/* /usr/share/doc/* /usr/share/man/* /usr/share/locale/* /var/cache/* /tmp/*

COPY --from=pydeps /opt/venv /opt/venv

# --- Hitch TLS cert ---
RUN (getent group _hitch || addgroup --system _hitch) \
    && (getent passwd _hitch || adduser --system --ingroup _hitch --no-create-home _hitch) \
    && openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
        -keyout /tmp/key.pem -out /tmp/cert.pem \
        -subj "/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
    && cat /tmp/cert.pem /tmp/key.pem > /etc/hitch/hitch.pem \
    && rm -f /tmp/cert.pem /tmp/key.pem \
    && chmod 644 /etc/hitch/hitch.pem

# --- MySQL config ---
COPY mariadb.cnf /etc/mysql/conf.d/server.cnf

# --- App ---
RUN (getent group varnish || addgroup --system varnish) \
    && (getent passwd varnish || adduser --system --ingroup varnish --no-create-home varnish) \
    && install -d -o varnish -g varnish /var/lib/varnish
RUN useradd -r -s /usr/sbin/nologin appuser
WORKDIR /app
COPY app.py .
COPY templates ./templates

# --- Bot ---
COPY bot.py /bot/bot.py

# --- Varnish VCL (backend = localhost) ---
COPY varnish.vcl /etc/varnish/default.vcl

# --- Hitch conf (backend = localhost) ---
COPY hitch.conf /etc/hitch/hitch.conf

# --- Supervisor ---
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 443

ENTRYPOINT ["/entrypoint.sh"]
