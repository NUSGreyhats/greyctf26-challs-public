FROM python:3.10-slim-bullseye

RUN apt-get update && apt-get install -y --no-install-recommends \
    xinetd python3 python3-pip && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -m 777 /app
WORKDIR /app

COPY . /app/
COPY caexor.xinetd /etc/xinetd.d/caexor

RUN chmod +x /app/chal.py

EXPOSE 30002

CMD ["xinetd", "-dontfork"]
# docker build -t caexor .
# docker run -d -p 20001:20001 caexor