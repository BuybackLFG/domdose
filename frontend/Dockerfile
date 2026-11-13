ARG NODE_IMAGE
FROM ${NODE_IMAGE} AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

ARG NGINX_IMAGE
FROM ${NGINX_IMAGE} AS runtime

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.conf /etc/nginx/security-headers.conf

RUN mkdir -p /logs && chown -R nginx:nginx /logs

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1/ready >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
