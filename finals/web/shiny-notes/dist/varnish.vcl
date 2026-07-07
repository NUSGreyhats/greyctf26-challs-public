vcl 4.1;

backend default {
    .host = "127.0.0.1";
    .port = "8080";
    .max_connections = 1;
}

sub vcl_recv {
    return (pass);
}

sub vcl_backend_fetch {
    unset bereq.http.X-Forwarded-For;
    unset bereq.http.X-Varnish;
}

sub vcl_deliver {
    unset resp.http.X-Varnish;
}
