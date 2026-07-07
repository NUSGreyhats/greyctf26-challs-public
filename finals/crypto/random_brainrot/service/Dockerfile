FROM python:3.10-slim

RUN apt-get update && apt-get install -y socat && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY server.py .
RUN chmod +x server.py

# Create a non-root user
RUN useradd -m ctf
USER ctf

EXPOSE 34067

# Run socat to listen on 34067 and execute the python script for every connection
CMD ["socat", "-T120", "TCP-LISTEN:34067,reuseaddr,fork,max-children=32", "EXEC:python3 -u server.py,stderr"]
