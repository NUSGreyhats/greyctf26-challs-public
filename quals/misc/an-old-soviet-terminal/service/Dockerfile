FROM ghcr.io/troupelang/troupe:latest

RUN apt-get update && apt-get install -y socat

WORKDIR /app

# Set up challenge files
COPY server.py .

COPY aliases.json .
COPY crtrp.sh .
COPY rtrp.sh .
COPY terminal.trp .
COPY ids/ ./ids/
COPY out/ ./out/
COPY trustmaps/ ./trustmaps/

RUN mkdir -p /tmp

RUN chmod +x server.py
RUN chmod +rwx /tmp
RUN chmod +x ./out
RUN chmod +x crtrp.sh rtrp.sh

EXPOSE 5000

CMD ["socat", "TCP-LISTEN:5000,reuseaddr,fork", "EXEC:python /app/server.py,stderr"]