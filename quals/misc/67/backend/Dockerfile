FROM node:24-alpine

WORKDIR /app

ENV HOST=0.0.0.0
ENV PORT=8787
ENV NODE_ENV=production

COPY --chown=node:node backend ./backend
COPY --chown=node:node frontend ./frontend
COPY --chown=node:node shared ./shared

USER node

EXPOSE 8787

CMD ["node", "backend/server.js"]
