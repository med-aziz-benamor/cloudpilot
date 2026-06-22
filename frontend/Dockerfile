# ═══════════════════════════════════════════════════════════════
# CloudPilot frontend — multi-stage (dev + prod targets)
# ═══════════════════════════════════════════════════════════════

# ─── Base with pnpm ───
FROM node:20-alpine AS base
RUN corepack enable && corepack prepare pnpm@9.1.4 --activate
WORKDIR /app

# ─── Dev target (hot reload via docker-compose) ───
FROM base AS dev
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install
COPY . .
EXPOSE 5173
CMD ["pnpm", "dev", "--host", "0.0.0.0", "--port", "5173"]

# ─── Build ───
FROM base AS build
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install
COPY . .
RUN pnpm build

# ─── Prod target (nginx serving static assets) ───
FROM nginx:alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
# SPA fallback so client routes resolve to index.html.
RUN printf 'server {\n  listen 80;\n  root /usr/share/nginx/html;\n  location / { try_files $uri /index.html; }\n}\n' \
    > /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
