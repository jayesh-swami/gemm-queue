import type { KernelRun } from '../api/types'
import { formatError, formatMs, formatSpeedup, formatTflops } from '../format'
import { StatusBadge } from './StatusBadge'

/** One row per kernel. Speedup is relative to the naive kernel. */
export function RunsTable({ runs }: { runs: KernelRun[] }) {
  const naiveMs = runs.find((r) => r.kernel === 'naive')?.ms ?? null

  return (
    <table className="runs">
      <thead>
        <tr>
          <th>Kernel</th>
          <th>Status</th>
          <th className="num">Time</th>
          <th className="num">TFLOPS</th>
          <th className="num">Speedup</th>
          <th className="num">Max error</th>
          <th>Check</th>
        </tr>
      </thead>
      <tbody>
        {runs.map((run) => (
          <tr key={run.id}>
            <td><code>{run.kernel}</code></td>
            <td><StatusBadge status={run.status} /></td>
            {run.error ? (
              <td colSpan={5} className="error">{run.error}</td>
            ) : (
              <>
                <td className="num">{formatMs(run.ms)}</td>
                <td className="num">{formatTflops(run.tflops)}</td>
                <td className="num">{formatSpeedup(naiveMs, run.ms)}</td>
                <td className="num">{formatError(run.max_error)}</td>
                <td><Check passed={run.passed} /></td>
              </>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Check({ passed }: { passed: boolean | null }) {
  if (passed === null) return <>–</>
  return passed ? <span className="pass">✓ correct</span> : <span className="fail">✗ wrong result</span>
}
