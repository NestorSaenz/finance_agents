# Safi frontend (Next.js) — container for Cloud Run.
# Multi-stage: install + build, then a slim runtime with the standalone output.

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Next.js bakes rewrite destinations at BUILD time, so the backend URL must be
# present here (not just at runtime). Override with --build-arg API_URL=... .
ARG API_URL=https://safi-backend-887687060494.us-central1.run.app
ENV API_URL=${API_URL}
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
# Next reads PORT at runtime; Cloud Run sets it (default 8080).
ENV PORT=8080

# Standalone server bundle + static assets + public files.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 8080
CMD ["node", "server.js"]
