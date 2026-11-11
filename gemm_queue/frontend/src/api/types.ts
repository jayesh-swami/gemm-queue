// Mirrors gemm_queue/api/schema.py.

export type Kernel = 'naive' | 'lds' | 'half2' | 'rocblas' | 'rocblas_half'

export type RunStatus = 'queued' | 'running' | 'done' | 'failed'

export const FINISHED: RunStatus[] = ['done', 'failed']

export interface JobRequest {
  m: number
  n: number
  k: number
  seed?: number
}

export interface JobCreated {
  job_id: number
  seed: number
}

export interface KernelRun {
  id: number
  kernel: Kernel
  status: RunStatus
  ms: number | null
  tflops: number | null
  max_error: number | null
  passed: boolean | null
  error: string | null
}

export interface JobDetail {
  job_id: number
  m: number
  n: number
  k: number
  seed: number
  status: RunStatus
  error: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  kernel_runs: KernelRun[]
}
