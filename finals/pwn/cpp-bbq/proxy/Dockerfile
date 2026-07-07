# syntax=docker/dockerfile:1

FROM python:3.14-slim

RUN id -u proxy >/dev/null 2>&1 \
    || useradd --create-home --home-dir /home/proxy --shell /usr/sbin/nologin proxy

COPY --chmod=0555 proxy/team_token_proxy.py /usr/local/bin/team_token_proxy.py

USER proxy

EXPOSE 1337

CMD ["python3", "/usr/local/bin/team_token_proxy.py"]
