# SPA: сборка Vite на Node 24 (lockfile создан npm 11) и отдача статикой через nginx.
# Контекст сборки — каталог frontend; карта берётся из public/maps и попадает в dist.
FROM node:24.22.3-alpine@sha256:116b800c3754b440ee0aa3ed2f20f5bf3d99a554bfd9adeea09ea8017f6e85f5 AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build

FROM nginx:1.30.6-alpine@sha256:901e593c95dc85f5a729f5765516321366ef4ac401821431d408897e95287d0a AS runtime

# Файловый журнал /var/log/domdossier/execution.log открывает master-процесс (root);
# каталог монтируется named volume frontend_logs и вне root документов.
RUN mkdir -p /var/log/domdossier

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
