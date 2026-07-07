FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends socat \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt

ENV PORT=1337
ENV SOCAT_CLOSE_TIMEOUT=20
ENV SOCAT_IDLE_TIMEOUT=1800
ENV SOCAT_MAX_CHILDREN=16
EXPOSE 1337

CMD ["sh", "-c", "exec socat -t ${SOCAT_CLOSE_TIMEOUT:-20} -T ${SOCAT_IDLE_TIMEOUT:-1800} TCP-LISTEN:${PORT:-1337},reuseaddr,fork,max-children=${SOCAT_MAX_CHILDREN:-16} EXEC:'python -u -m server.cli.app --headless --pow --no-color --team-token',stderr"]
