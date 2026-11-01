# syntax=docker/dockerfile:1.7
# Builds both SPAs and serves them (plus the reverse proxy) with Nginx.
FROM docker.io/library/node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json frontend/tsconfig.base.json ./
COPY frontend/packages ./packages
COPY frontend/apps/miniapp/package.json apps/miniapp/
COPY frontend/apps/dashboard/package.json apps/dashboard/
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY frontend/apps ./apps
RUN npm run build -w @sop/miniapp && npm run build -w @sop/dashboard

FROM docker.io/library/nginx:1.27-alpine
COPY infra/nginx/nginx.conf /etc/nginx/nginx.conf
COPY infra/nginx/templates /etc/nginx/templates
COPY infra/nginx/snippets /etc/nginx/snippets
COPY infra/nginx/entrypoint/15-resolver.envsh /docker-entrypoint.d/15-resolver.envsh
COPY --from=build /app/apps/miniapp/dist /srv/miniapp
COPY --from=build /app/apps/dashboard/dist /srv/dashboard
EXPOSE 80 443
