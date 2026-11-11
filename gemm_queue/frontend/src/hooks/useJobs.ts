import { useEffect, useState } from 'react'

import { listJobs } from '../api/jobs'
import type { JobDetail } from '../api/types'

const LIMIT = 50
const POLL_MS = 3000

/** The latest jobs, refreshed every few seconds while the caller is mounted. */
export function useJobs() {
  const [jobs, setJobs] = useState<JobDetail[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined

    async function poll() {
      try {
        const next = await listJobs(LIMIT)
        if (cancelled) return
        setJobs(next)
        setError(null)
      } catch (e) {
        if (!cancelled) setError((e as Error).message)
      }
      if (!cancelled) timer = window.setTimeout(poll, POLL_MS)
    }

    poll()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [])

  return { jobs, error }
}
