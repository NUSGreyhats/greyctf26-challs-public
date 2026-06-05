FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends socat \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY dist/requirements.txt .
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt
COPY dist/ .

ENV FLAG=CTF{set_FLAG_env_on_the_remote_service}
EXPOSE 38267

CMD ["sh", "-c", "exec socat TCP-LISTEN:38267,reuseaddr,fork EXEC:'python3 /app/server.py',stderr"]
