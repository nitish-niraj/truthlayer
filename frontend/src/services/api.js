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
 * V2 Phase 1: validate an uploaded image and return its metadata.
 * Supports PNG, JPG, JPEG, WEBP up to 5MB. The endpoint does NOT run OCR
 * or vision analysis — it only confirms the file is a real, uncorrupted
 * image in an allowed format.
 */
export async function uploadImage(file) {
  if (!file) {
    throw new Error('No file provided')
  }
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post('/api/upload-image', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data // { filename, file_type, mime_type, size_bytes }
}

/**
 * V2 Phase 2: send an image to Kimi K2.6 vision and get back the verifiable
 * factual claims it can see. No web search, no verdict — just the claim
 * list. The Vision API can take 10-30s on first call, so the timeout is
 * generous.
 */
export async function extractImageClaims(file) {
  if (!file) {
    throw new Error('No file provided')
  }
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post('/api/extract-image-claims', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 90_000,
  })
  return data // { filename, claims: ExtractedClaim[] }
}

/**
 * V2 Phase 3: end-to-end image verification. Validates the image, extracts
 * claims via Kimi Vision, then runs every claim through the SAME search +
 * verdict engine the PDF pipeline uses. Returns the full report in the
 * exact same shape as the PDF verify response so the ResultsDashboard
 * can render either source without branching.
 *
 * Latency budget: 30-60s (vision + per-claim search + verdict). Timeout
 * is set conservatively to survive Render free-tier cold start.
 */
export async function verifyImage(file) {
  if (!file) {
    throw new Error('No file provided')
  }
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post('/api/verify-image', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000,
  })
  return data // { filename, summary, claims: VerifiedClaim[] }
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
 *
 * Resilient to transient network errors and 404s (which can happen if the
 * Render worker restarts mid-run and clears the in-memory job store): a
 * single transient failure is logged and the loop retries up to
 * ``maxConsecutiveErrors`` times in a row before surfacing a hard error.
 * This prevents the user from being kicked to the error screen by a brief
 * network blip or a worker recycle on Render's free tier.
 */
export async function pollVerifyUntilDone(job_id, {
  intervalMs = 1500,
  timeoutMs = 120_000,
  onProgress,
  maxConsecutiveErrors = 5,
} = {}) {
  const deadline = Date.now() + timeoutMs
  let consecutiveErrors = 0
  // eslint-disable-next-line no-constant-condition
  while (true) {
    if (Date.now() > deadline) {
      throw new Error('Analysis timed out. Please try again.')
    }
    let payload
    try {
      payload = await getVerifyStatus(job_id)
      consecutiveErrors = 0
    } catch (err) {
      consecutiveErrors += 1
      const status = err?.response?.status
      // 404 means the job_id is gone (Render worker recycled and lost the
      // in-memory store). One more poll attempt before giving up so we
      // don't bail out on a transient race.
      if (status === 404 && consecutiveErrors >= 2) {
        throw new Error(
          'The analysis job was lost (server restarted). Please upload again.',
        )
      }
      if (consecutiveErrors >= maxConsecutiveErrors) {
        throw new Error(
          'Lost connection to the verification server. Please try again.',
        )
      }
      // Wait a beat and try again.
      await new Promise((resolve) => setTimeout(resolve, intervalMs))
      continue
    }
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

/**
 * V2 Phase 5: translate a thrown error from one of the verify/upload/extract
 * calls into a user-facing string the ErrorScreen can render directly.
 *
 * Distinguishes between:
 *   - "You appear to be offline" (navigator.onLine === false)
 *   - "Server unavailable" (network error with no response)
 *   - "Server timed out" (axios code === 'ECONNABORTED')
 *   - HTTP error envelopes from the backend ({ detail, error })
 *   - Anything else: the raw error.message
 *
 * Keeps the messaging short and actionable — the ErrorScreen adds the
 * "Retry" CTA on top, so we don't have to prompt the user to retry here.
 */
export function describeNetworkError(err) {
  // Offline is the most common cause of "Failed to fetch" on laptops and
  // a clean, user-friendly first guess.
  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    return "You're offline. Reconnect to the internet and try again."
  }
  const status = err?.response?.status
  const data = err?.response?.data
  // Backend error envelope (FastAPI HTTPException detail).
  if (data && typeof data === 'object') {
    if (typeof data.detail === 'string' && data.detail) {
      return data.detail
    }
    if (typeof data.detail === 'object' && data.detail !== null) {
      const detailObj = data.detail
      if (typeof detailObj.detail === 'string' && detailObj.detail) {
        return detailObj.detail
      }
    }
    if (typeof data.error === 'string' && data.error && data.detail) {
      return String(data.detail)
    }
  }
  // Axios timeout.
  if (err?.code === 'ECONNABORTED') {
    return 'The server took too long to respond. Please try again.'
  }
  // Network error: server down, CORS, DNS, etc. axios throws with no
  // response attached.
  if (err?.request && !err?.response) {
    return 'The verification server is unavailable. Please try again in a moment.'
  }
  if (typeof status === 'number' && status >= 500) {
    return 'The verification server hit an unexpected error. Please try again.'
  }
  if (err?.message) {
    return String(err.message)
  }
  return 'Something went wrong. Please try again.'
}
