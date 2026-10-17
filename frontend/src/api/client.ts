export interface ApiErrorBody {
  code: string
  message: string
  request_id: string | null
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: ApiErrorBody,
  ) {
    super(body.message)
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, { credentials: 'same-origin', ...init })
  } catch {
    throw new ApiError(0, { code: 'NETWORK_ERROR', message: 'API unreachable', request_id: null })
  }
  const text = await res.text()
  const json = text ? safeJson(text) : null
  if (!res.ok) {
    const body = (json as { error?: ApiErrorBody } | null)?.error
    // /health/ready intentionally returns 503 with a useful body; surface it as data.
    if (path.startsWith('/health/') && json) return json as T
    throw new ApiError(
      res.status,
      body ?? { code: 'HTTP_ERROR', message: `HTTP ${res.status}`, request_id: null },
    )
  }
  return json as T
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

export interface LiveHealth {
  status: 'alive'
  time: string
}
export interface ReadyHealth {
  status: string
  components: Record<string, string>
  detail?: string
}

export const getLive = () => api<LiveHealth>('/health/live')
export const getReady = () => api<ReadyHealth>('/health/ready')
