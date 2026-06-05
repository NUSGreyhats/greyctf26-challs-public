FROM python:3.10-slim

RUN apt-get update && apt-get install -y socat && rm -rf /var/lib/apt/lists/*
RUN pip install pycryptodome

WORKDIR /app
COPY server.py .
RUN chmod +x server.py

# Create a non-root user
RUN useradd -m ctf
USER ctf

EXPOSE 37167

# Run socat to listen on 37167 and execute the python script for every connection
CMD ["socat", "TCP-LISTEN:37167,reuseaddr,fork", "EXEC:'python3 server.py'"]