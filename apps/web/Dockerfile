FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# NEXT_PUBLIC_* variables are inlined into the client JS bundle at BUILD time
# (next build), not read at container runtime — so this must be available
# BEFORE `npm run build`, not just in the final image's `environment:`.
# Defaults to the existing runtime fallback (http://localhost:8000, same as
# apps/web/src/lib/api.ts and next.config.js) so local/default builds are
# unchanged; pass --build-arg NEXT_PUBLIC_API_URL=https://your-api.example.com
# (or docker-compose build args) to bake in the real deployed API origin.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000

COPY --from=builder /app/package*.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["npm", "start"]
