FROM ubuntu:22.04 AS app
RUN apt-get update && apt-get install locales-all -y && rm -rf /var/lib/apt/lists/* 

FROM pwn.red/jail
COPY --from=app / /srv
COPY ./elite_ball_knowledge /srv/app/run
COPY ./flag.txt /srv/app/flag.txt
RUN chmod +x /srv/app/run
RUN chmod 644 /srv/app/flag.txt