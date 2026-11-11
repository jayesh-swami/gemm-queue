import { useJob } from '../hooks/useJob'
import { RunsTable } from './RunsTable'
import { StatusBadge } from './StatusBadge'

/** A job's header and its runs, refreshed until the job finishes. */
export function JobView({ jobId }: { jobId: number }) {
  const { job, error } = useJob(jobId)

  if (error) return <p className="error">Job {jobId}: {error}</p>
  if (!job) return <p>Loading job {jobId}…</p>

  const took = job.finished_at
    ? `${((Date.parse(job.finished_at) - Date.parse(job.created_at)) / 1000).toFixed(1)} s`
    : null

  return (
    <section className="job">
      <h2>
        Job {job.job_id} <StatusBadge status={job.status} />
      </h2>
      <p className="meta">
        {job.m} × {job.k} @ {job.k} × {job.n} · seed {job.seed}
        {took && ` · took ${took}`}
      </p>
      <RunsTable runs={job.kernel_runs} />
    </section>
  )
}
