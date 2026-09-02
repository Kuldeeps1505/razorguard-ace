# RazorGuard control-plane UI
# Multi-stage: Vite build → nginx (SPA + API reverse proxy)

FROM node:22-alpine AS build
WORKDIR /ui

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
RUN apk add --no-cache wget

COPY infrastructure/docker/nginx.proxy_params /etc/nginx/proxy_params
COPY infrastructure/docker/nginx.ui.conf /etc/nginx/conf.d/default.conf
COPY --from=build /ui/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
