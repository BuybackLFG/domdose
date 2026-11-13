# Сборка: docker build -t domdose-frontend ./frontend
# Статика отдаётся nginx; /api проксируется на backend (см. nginx.conf).
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# В контейнере фронтенд ходит в API по относительному пути /api,
# который nginx проксирует на сервис backend.
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
