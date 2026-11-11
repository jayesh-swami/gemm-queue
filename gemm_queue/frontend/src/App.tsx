import { useState } from 'react'

import { JobForm } from './components/JobForm'
import { JobView } from './components/JobView'

// The job id lives in the URL (?job=18), so a reload or a shared link shows the same job.
function jobIdFromUrl(): number | null {
  const id = Number(new URLSearchParams(window.location.search).get('job'))
  return Number.isInteger(id) && id > 0 ? id : null
}

export default function App() {
  const [jobId, setJobId] = useState(jobIdFromUrl)

  function handleCreated(id: number) {
    window.history.pushState(null, '', `?job=${id}`)
    setJobId(id)
  }

  return (
    <main>
      <h1>gemm-queue</h1>
      <p className="intro">
        Runs C = A × B with five GPU kernels on random matrices and checks each result against NumPy.
      </p>
      <JobForm onCreated={handleCreated} />
      {/* key: a new job id gets a fresh JobView, so old results don't linger */}
      {jobId !== null && <JobView key={jobId} jobId={jobId} />}
    </main>
  )
}
