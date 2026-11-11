import { useEffect, useState } from 'react'

import { JobForm } from './components/JobForm'
import { JobHistory } from './components/JobHistory'
import { JobView } from './components/JobView'
import { Tabs, type Tab } from './components/Tabs'

interface View {
  tab: Tab
  jobId: number | null
}

// The view lives in the URL (?tab=history&job=18), so reloads, shared links and
// the back button all work.
function viewFromUrl(): View {
  const params = new URLSearchParams(window.location.search)
  const id = Number(params.get('job'))
  return {
    tab: params.get('tab') === 'history' ? 'history' : 'run',
    jobId: Number.isInteger(id) && id > 0 ? id : null,
  }
}

function urlFor(view: View): string {
  const params = new URLSearchParams()
  if (view.tab === 'history') params.set('tab', 'history')
  if (view.jobId !== null) params.set('job', String(view.jobId))
  const query = params.toString()
  return query ? `?${query}` : window.location.pathname
}

export default function App() {
  const [view, setView] = useState(viewFromUrl)

  useEffect(() => {
    const onPopState = () => setView(viewFromUrl())
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  function navigate(next: View) {
    window.history.pushState(null, '', urlFor(next))
    setView(next)
  }

  return (
    <main>
      <h1>gemm-queue</h1>
      <p className="intro">
        Runs C = A × B with five GPU kernels on random matrices and checks each result against NumPy.
      </p>
      <Tabs active={view.tab} onChange={(tab) => navigate({ tab, jobId: null })} />

      {view.tab === 'run' && (
        <JobForm onCreated={(jobId) => navigate({ tab: 'run', jobId })} />
      )}
      {view.tab === 'history' && (
        <JobHistory
          selectedId={view.jobId}
          onSelect={(jobId) => navigate({ tab: 'history', jobId })}
        />
      )}

      {/* key: a new job id gets a fresh JobView, so old results don't linger */}
      {view.jobId !== null && <JobView key={view.jobId} jobId={view.jobId} />}
    </main>
  )
}
