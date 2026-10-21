import { createFileRoute } from '@tanstack/react-router'
import { proxyApi } from '../server/api-proxy'

export const Route = createFileRoute('/api/$')({
  server: {
    handlers: {
      GET: ({ request }) => proxyApi(request),
      POST: ({ request }) => proxyApi(request),
      PATCH: ({ request }) => proxyApi(request),
      PUT: ({ request }) => proxyApi(request),
      DELETE: ({ request }) => proxyApi(request),
    },
  },
})
