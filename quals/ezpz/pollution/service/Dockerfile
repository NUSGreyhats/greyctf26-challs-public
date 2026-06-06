FROM node:lts-trixie-slim AS app

WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev
COPY app.js db.js options.js passport.js secrets.js seed.js util.js ./
COPY routes ./routes
COPY views ./views
COPY public ./public


FROM node:lts-trixie-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates gosu wget \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=app /app /app
COPY install-flag.sh /usr/local/bin/install-flag.sh
RUN chown root:root / \
  && chmod go-w / \
  && chmod 755 /usr/local/bin/install-flag.sh \
  && mkdir -p public/images/profileImages uploads \
  && useradd --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin appuser \
  && chown -R root:root /app \
  && chown -R appuser:appuser public/images/profileImages uploads \
  && chmod -R 755 /app \
  && chmod -R 775 public/images/profileImages uploads \
  && chmod 555 /tmp /var/tmp \
  && if [ -d /run/lock ]; then chmod 555 /run/lock; fi \
  && (find / -xdev -type f -perm /6000 ! -path /usr/sbin/gosu ! -path /usr/bin/gosu -exec chmod a-s {} + || true)

EXPOSE 3000

ENTRYPOINT ["/usr/local/bin/install-flag.sh"]
CMD ["npm", "start"]
