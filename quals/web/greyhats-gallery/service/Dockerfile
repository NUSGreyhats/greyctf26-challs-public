FROM --platform=linux/amd64 node:lts-trixie-slim@sha256:c70f2d9b9dcd1f95d51b1f2d9c000637f203dbe2cbeaf06680780584518ca5c3 AS app

WORKDIR /app

COPY package*.json ./
COPY post_build/patch-ejs-whitelist.js ./post_build/patch-ejs-whitelist.js
RUN npm ci --omit=dev \
  && node ./post_build/patch-ejs-whitelist.js ./node_modules/ejs/lib/ejs.js \
  && rm -rf ./post_build
COPY src ./src
COPY views ./views


FROM --platform=linux/amd64 node:lts-trixie-slim@sha256:c70f2d9b9dcd1f95d51b1f2d9c000637f203dbe2cbeaf06680780584518ca5c3

LABEL org.opencontainers.image.base.name="docker.io/library/node:lts-trixie-slim" \
  org.opencontainers.image.base.digest="sha256:c70f2d9b9dcd1f95d51b1f2d9c000637f203dbe2cbeaf06680780584518ca5c3" \
  org.opencontainers.image.base.revision="58635ae7aaeab55a5c036b59e8ca93d864119cbe"

RUN apt-get update \
  && apt-get install -y --no-install-recommends gosu unzip \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=app /app /app
COPY flag.txt /flag-seed.txt
COPY install-flag.sh /usr/local/bin/install-flag.sh
RUN chown root:root / \
  && chmod go-w / \
  && chown root:root /flag-seed.txt \
  && chmod 400 /flag-seed.txt \
  && chmod 755 /usr/local/bin/install-flag.sh \
  && mkdir -p /app/uploads \
  && useradd --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin appuser \
  && chown -R root:root /app \
  && chown -R appuser:appuser /app/uploads \
  && chown root:appuser /app/views \
  && chmod -R 755 /app \
  && chmod -R 775 /app/uploads \
  && chmod 1775 /app/views \
  && chmod 644 /app/views/*.ejs \
  && chmod 555 /tmp /var/tmp \
  && if [ -d /run/lock ]; then chmod 555 /run/lock; fi \
  && (find / -xdev -type f -perm /6000 ! -path /usr/sbin/gosu ! -path /usr/bin/gosu -exec chmod a-s {} + || true)

EXPOSE 3000

ENTRYPOINT ["/usr/local/bin/install-flag.sh"]
CMD ["node", "src/server.js"]
