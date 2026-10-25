FROM node:20-slim AS build
WORKDIR /app
COPY frontend-v2/package.json frontend-v2/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend-v2 ./
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
