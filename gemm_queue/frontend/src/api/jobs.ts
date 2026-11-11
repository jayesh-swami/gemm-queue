import type { JobCreated, JobDetail, JobRequest } from './types'

export function createJob(req: JobRequest): Promise<JobCreated> {
  return request('/jobs', { method: 'POST', body: JSON.stringify(req) })
}

export function getJob(jobId: number): Promise<JobDetail> {
  return request(`/jobs/${jobId}`)
}

// Same origin as the page: FastAPI serves both (Vite proxies /jobs in dev).
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': import.meta.env.VITE_API_KEY,
    },
  })
  if (!res.ok) {
    throw new Error(await errorMessage(res))
  }
  return (await res.json()) as T
}

// FastAPI errors look like {"detail": "..."}, or for validation errors
// {"detail": [{"loc": [..., "m"], "msg": "..."}]}.
async function errorMessage(res: Response): Promise<string> {
  const body = await res.json().catch(() => null)
  const detail = body?.detail
  if (typeof detail === 'string') {
    return detail
  }
  if (Array.isArray(detail)) {
    return detail.map((d) => `${d.loc.at(-1)}: ${d.msg}`).join(', ')
  }
  return `${res.status} ${res.statusText}`
}
