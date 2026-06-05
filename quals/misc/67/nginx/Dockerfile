FROM nginxinc/nginx-unprivileged:1.27-alpine

USER root

RUN apk add --no-cache su-exec \
  && sed -i \
    -e 's|error_log  /var/log/nginx/error.log notice;|error_log /tmp/nginx-logs/error.log notice;|' \
    -e 's|access_log  /var/log/nginx/access.log  main;|access_log /tmp/nginx-logs/access.log main;|' \
    /etc/nginx/nginx.conf

COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY nginx/docker-entrypoint.sh /usr/local/bin/docker-entrypoint-le.sh
RUN chmod +x /usr/local/bin/docker-entrypoint-le.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint-le.sh"]
CMD ["nginx", "-g", "daemon off;"]
