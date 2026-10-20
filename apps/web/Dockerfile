FROM node:24.18.1-alpine3.23@sha256:c2cc26d8f991c2db236ad51a61efee843c482372d6d22570787309d511694110 AS build
ENV PNPM_HOME="/pnpm" PATH="/pnpm:$PATH"
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/api-client/package.json packages/api-client/package.json
RUN pnpm install --frozen-lockfile
COPY apps/web apps/web
COPY packages/api-client packages/api-client
ARG VITE_API_URL=http://localhost:8000
ARG VITE_AUTH_MODE=password
ARG VITE_INVITATION_EMAIL=
ENV VITE_INVITATION_EMAIL=$VITE_INVITATION_EMAIL
ENV VITE_API_URL=$VITE_API_URL VITE_AUTH_MODE=$VITE_AUTH_MODE
RUN pnpm --filter @resolve-flow/web build

FROM node:24.18.1-alpine3.23@sha256:c2cc26d8f991c2db236ad51a61efee843c482372d6d22570787309d511694110 AS runtime
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3000
WORKDIR /app
COPY --from=build --chown=node:node /app/apps/web/.output ./.output
USER node
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 CMD ["node", "--input-type=module", "-e", "const r = await fetch('http://127.0.0.1:' + process.env.PORT + '/', {signal: AbortSignal.timeout(4000)}); if (!r.ok) process.exit(1)"]
CMD ["node", ".output/server/index.mjs"]
