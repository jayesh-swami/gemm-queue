import { useEffect, useState } from 'react'

import { getJob } from '../api/jobs'
import { FINISHED, type JobDetail } from '../api/types'

const POLL_MS = 1000

/** Polls a job every second until it's done or failed. */
export function useJob(jobId: number) {
  const [job, setJob] = useState<JobDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined

    async function poll() {
      try {
        const next = await getJob(jobId)
        if (cancelled) return
        setJob(next)
        if (!FINISHED.includes(next.status)) {
          timer = window.setTimeout(poll, POLL_MS)
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message)
      }
    }

    poll()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [jobId])

  return { job, error }
}
