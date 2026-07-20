FROM node:20-bookworm-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && chown -R node:node /app
COPY --chown=node:node server.js ./

USER node
EXPOSE 8080 8081
HEALTHCHECK --interval=3s --timeout=2s --retries=20 \
  CMD node -e "require('http').get('http://127.0.0.1:8081/health', r => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"
CMD ["node", "server.js"]
