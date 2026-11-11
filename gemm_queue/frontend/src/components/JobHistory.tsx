import type { JobDetail } from '../api/types'
import { formatTflops, formatTime } from '../format'
import { useJobs } from '../hooks/useJobs'
import { StatusBadge } from './StatusBadge'

/** Recent jobs; clicking one opens its runs below the list. */
export function JobHistory(props: { selectedId: number | null; onSelect: (jobId: number) => void }) {
  const { jobs, error } = useJobs()

  if (error) return <p className="error">{error}</p>
  if (!jobs) return <p>Loading jobs…</p>
  if (jobs.length === 0) return <p className="meta">No jobs yet.</p>

  return (
    <table className="runs history">
      <thead>
        <tr>
          <th>Job</th>
          <th>M × N × K</th>
          <th>Status</th>
          <th>Submitted</th>
          <th className="num">Fastest</th>
        </tr>
      </thead>
      <tbody>
        {jobs.map((job) => (
          <tr
            key={job.job_id}
            className={job.job_id === props.selectedId ? 'selected' : undefined}
            onClick={() => props.onSelect(job.job_id)}
          >
            <td>
              <a
                href={`?tab=history&job=${job.job_id}`}
                onClick={(e) => {
                  e.preventDefault()
                  props.onSelect(job.job_id)
                }}
              >
                #{job.job_id}
              </a>
            </td>
            <td>{job.m} × {job.n} × {job.k}</td>
            <td><StatusBadge status={job.status} /></td>
            <td>{formatTime(job.created_at)}</td>
            <td className="num">{fastest(job)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// The quickest run that finished with a correct result.
function fastest(job: JobDetail): string {
  const ok = job.kernel_runs.filter((r) => r.passed && r.tflops !== null)
  if (ok.length === 0) return '–'
  const best = ok.reduce((a, b) => (b.tflops! > a.tflops! ? b : a))
  return `${formatTflops(best.tflops)} TFLOPS · ${best.kernel}`
}
