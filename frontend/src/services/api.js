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

export async function verifyDocument(text, filename) {
  if (!text || !filename) {
    throw new Error('Missing document text or filename')
  }
  // The backend has a 25s hard server-side cap. The frontend cap is 28s so
  // the user sees a clean "timeout" error instead of the connection being
  // cut by Render. If the backend returns early with a partial response
  // (which it now does on budget exhaustion), the response is still valid
  // and the results screen will render whatever claims finished.
  const { data } = await api.post(
    '/api/verify',
    { text, filename },
    { timeout: 28_000 }
  )
  return data
}
