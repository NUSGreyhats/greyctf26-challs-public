FROM debian@sha256:0104b334637a5f19aa9c983a91b54c89887c0984081f2068983107a6f6c21eeb

RUN apt-get update && \
    apt-get install -y g++ lighttpd && \
    rm -rf /var/lib/apt/lists/*

COPY index.cpp /tmp/index.cpp
RUN g++ -std=c++17 -static -o /var/www/html/index.cgi -fstack-protector-strong -no-pie /tmp/index.cpp && \
    chown root:root /var/www/html/index.cgi && \
    chmod 555 /var/www/html/index.cgi && \
    rm /tmp/index.cpp

COPY flag.txt /flag.txt
RUN chmod 444 /flag.txt && chown root:root /flag.txt
COPY lighttpd.conf /etc/lighttpd/lighttpd.conf

RUN useradd -r -M -d /nonexistent -s /usr/sbin/nologin ctf && \
    chown -R root:root /var/www/html /etc/lighttpd && \
    chmod 555 /var/www/html && \
    chmod 444 /etc/lighttpd/lighttpd.conf

EXPOSE 8080
USER ctf

CMD ["lighttpd", "-D", "-f", "/etc/lighttpd/lighttpd.conf"]
