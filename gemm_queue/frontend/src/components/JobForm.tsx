import { useState, type FormEvent } from 'react'

import { createJob } from '../api/jobs'

// Same limit as MAX_DIM in gemm_queue/api/constants.py; the API enforces it.
const MAX_DIM = 8192

/** M, N, K and an optional seed. Submits the job and reports its id. */
export function JobForm({ onCreated }: { onCreated: (jobId: number) => void }) {
  const [m, setM] = useState('1024')
  const [n, setN] = useState('1024')
  const [k, setK] = useState('1024')
  const [seed, setSeed] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const job = await createJob({
        m: Number(m),
        n: Number(n),
        k: Number(k),
        seed: seed === '' ? undefined : Number(seed),
      })
      onCreated(job.job_id)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="job-form" onSubmit={handleSubmit}>
      <DimInput label="M" value={m} onChange={setM} />
      <DimInput label="N" value={n} onChange={setN} />
      <DimInput label="K" value={k} onChange={setK} />
      <label>
        Seed
        <input
          type="number"
          min={0}
          placeholder="random"
          value={seed}
          onChange={(e) => setSeed(e.target.value)}
        />
      </label>
      <button type="submit" disabled={submitting}>
        {submitting ? 'Submitting…' : 'Run'}
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  )
}

function DimInput(props: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label>
      {props.label}
      <input
        type="number"
        required
        min={1}
        max={MAX_DIM}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
      />
    </label>
  )
}
