import axios from 'axios'

const baseURL = import.meta.env.VITE_API_URL
if (!baseURL) {
  throw new Error(
    'VITE_API_URL is not set. Configure it in your Vercel project settings ' +
    '(or in frontend/.env for local dev). See frontend/.env.example.'
  )
}

const api = axios.create({
  baseURL,
  timeout: 30_000,
})

export default api

export async function uploadPDF(file) {
  if (!file) {
    throw new Error('No file provided')
  }
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post('/api/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

/**
 * Start a background verification job. Returns immediately (<100ms) with a
 * job_id; the heavy work runs server-side and the client polls
 * getVerifyStatus(job_id) for progress and the final result.
 *
 * The previous synchronous /api/verify endpoint was killed by Render's
 * 30s free-tier proxy timeout whenever the LLM cold-start pushed the
 * pipeline past that wall. The background-job pattern decouples the
 * request lifetime from the pipeline lifetime.
 */
export async function startVerify(text, filename) {
  if (!text || !filename) {
    throw new Error('Missing document text or filename')
  }
  const { data } = await api.post(
    '/api/verify',
    { text, filename },
    { timeout: 15_000 }
  )
  return data // { job_id, status: 'pending' }
}

/**
 * Poll a background job for its current state.
 * Returns the raw server payload:
 *   { job_id, status, progress?, result?, error?, ... }
 *
 * status is one of: 'pending' | 'running' | 'completed' | 'partial' | 'failed'
 */
export async function getVerifyStatus(job_id) {
  if (!job_id) {
    throw new Error('job_id is required')
  }
  const { data } = await api.get(`/api/verify/${job_id}`, { timeout: 10_000 })
  return data
}

/**
 * Convenience wrapper: poll until the job reaches a terminal state or the
 * caller-supplied timeout elapses. Yields each intermediate payload via
 * onProgress so the UI can advance its stepper as the server reports
 * progress. Throws on 'failed' status; returns the result on
 * 'completed' or 'partial'.
 */
export async function pollVerifyUntilDone(job_id, {
  intervalMs = 1500,
  timeoutMs = 120_000,
  onProgress,
} = {}) {
  const deadline = Date.now() + timeoutMs
  // eslint-disable-next-line no-constant-condition
  while (true) {
    if (Date.now() > deadline) {
      throw new Error('Analysis timed out. Please try again.')
    }
    const payload = await getVerifyStatus(job_id)
    onProgress?.(payload)
    if (payload.status === 'completed' || payload.status === 'partial') {
      return payload.result
    }
    if (payload.status === 'failed') {
      throw new Error(payload.error || 'Verification failed.')
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
}
