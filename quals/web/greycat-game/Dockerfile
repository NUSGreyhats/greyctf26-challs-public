FROM node:24-alpine

WORKDIR /app

COPY --chown=node:node service/ ./

ENV PORT=4173

EXPOSE 4173

USER node

CMD ["node", "serve-local.js"]
