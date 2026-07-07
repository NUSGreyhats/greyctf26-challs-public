# Name

Shiny Notes

# Description
Blazing fast, password-encrypted notes. The admin trusts it with a secret, but not the flag.

TLS certificate errors are expected for this challenge and can be ignored.
Chrome is recommended for accessing the challenge.

# Author

jro

# Flag

`grey{master_of_http_and_sql_smuggling_UUID}`

# Whale

enabled: true
redirect_type: https
redirect_port: 443
memory_limit: 1g
cpu_limit: 1.0

# Deployment

The challenge is packaged as a single service image containing Hitch, Varnish 8.0.1, Flask, MariaDB, and the admin bot. Deploy the private service build with:

```bash
docker compose up --build
```

The admin bot registers a fresh account every 10 seconds using the `FLAG` as the password. The flag lands in `localStorage` under `notes_password` on the challenge origin.

Required environment:

- `FLAG`: the flag value (used as the admin bot's password).

# Structure

- `service/`: private deployment source.
- `dist/`: player-facing build context with a fake default flag.
- `solve/`: single end-to-end exploit used for validation.
