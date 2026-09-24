# ResolveFlow API client

`createApiClient(baseUrl)` returns an `openapi-fetch` client with paths, request
bodies, and responses typed from the API's OpenAPI document. Pass a bearer token
through a request's `headers` option when calling customer routes.

```ts
import { createApiClient } from '@resolve-flow/api-client'

const api = createApiClient('http://localhost:8000')
const { data, error } = await api.GET('/issue-reports/', {
  headers: { Authorization: 'Bearer demo-token' },
})
```

From the repository root, run `pnpm generate:api-client` after API changes.
This exports `openapi.json` directly from the FastAPI factory and regenerates
`src/schema.d.ts`. Both files are checked in. `pnpm check:api-client` verifies
both files match the source; it does not need a running API or database.
