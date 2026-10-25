FROM node:20-slim
WORKDIR /app
COPY services/hmem-sidecar/package.json ./
RUN npm install --no-audit --no-fund
# Vendors the Meterless H-MEM reference engine (Apache-2.0) exactly as the official starter does.
RUN npm run setup
COPY services/hmem-sidecar/server.ts ./
ENV HMEM_HOST=0.0.0.0 HMEM_STATE_DIR=/data
EXPOSE 8765
CMD ["npx", "tsx", "server.ts"]
