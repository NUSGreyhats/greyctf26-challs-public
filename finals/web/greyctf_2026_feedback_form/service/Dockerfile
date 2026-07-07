FROM python:3.12-slim

WORKDIR /app

ENV NETRC=/app/.netrc

RUN pip install --no-cache-dir flask requests==2.34.2

COPY server.py .netrc title.png ./
COPY templates ./templates

EXPOSE 8000

CMD ["python", "server.py"]
