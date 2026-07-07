FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y lighttpd && rm -rf /var/lib/apt/lists/*
COPY lua /usr/local/bin/lua
COPY index.cgi /var/www/cgi-bin/index.cgi
COPY lighttpd.conf /etc/lighttpd/lighttpd.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /usr/local/bin/lua /var/www/cgi-bin/index.cgi /entrypoint.sh && \
    chown www-data:www-data /var/www/cgi-bin/index.cgi
EXPOSE 80
ENTRYPOINT ["/entrypoint.sh"]
