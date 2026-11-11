export function formatMs(ms: number | null): string {
  if (ms === null) return '–'
  return ms >= 100 ? `${ms.toFixed(0)} ms` : `${ms.toFixed(2)} ms`
}

export function formatTflops(tflops: number | null): string {
  return tflops === null ? '–' : tflops.toFixed(2)
}

export function formatError(maxError: number | null): string {
  return maxError === null ? '–' : maxError.toExponential(1)
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function formatSpeedup(naiveMs: number | null, ms: number | null): string {
  if (naiveMs === null || ms === null) return '–'
  return `${(naiveMs / ms).toFixed(1)}×`
}
