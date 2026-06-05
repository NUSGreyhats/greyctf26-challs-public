# baby-bof

A tiny CGI service protects the flag with HTTP Basic authentication.

The flag is in `/flag.txt` on the server.

## Running locally

```sh
docker compose up --build
```

The service listens on port `32367` on the host and port `8080` in the container.

## Files

```text
index.cpp           CGI service source
Dockerfile          local web runner
docker-compose.yml  local runner compose file
lighttpd.conf       web server configuration
flag.txt            local testing flag
```
