FROM python:3.12-alpine AS python

FROM pwn.red/jail
COPY --from=python / /srv
COPY run.sh /srv/app/run
COPY server.py /srv/app/server.py
COPY flag.txt /srv/app/
RUN mkdir -p /srv/app/logs && \
    cp /srv/app/*.txt /srv/app/logs/err.log && \
    chmod 444 /srv/app/logs/* && \
    chmod 755 /srv/app/run && \
    chmod 755 /srv/app/run

ENV JAIL_MEM=0
ENV JAIL_CPU=100
ENV JAIL_TIME=70