const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export async function apiRequest(path, options = {}) {
  const headers = new Headers(options.headers || {})
  headers.set('Accept', 'application/json')
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const token = localStorage.getItem('hhx_access_token')
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(`${apiBaseUrl}${path}`, { ...options, headers })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || '請求失敗，請稍後再試')
  }
  return payload
}

export async function login(username, password) {
  return apiRequest('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export async function getCurrentTeacher() {
  return apiRequest('/api/auth/me')
}

export async function getQuestionSets() {
  return apiRequest('/api/question-sets')
}

export async function getQuestionSet(id) {
  return apiRequest(`/api/question-sets/${id}`)
}

export async function previewQuestionSet(file) {
  const body = new FormData()
  body.append('file', file)
  return apiRequest('/api/question-sets/preview', { method: 'POST', body })
}

export async function importQuestionSet(name, file) {
  const body = new FormData()
  body.append('name', name)
  body.append('file', file)
  return apiRequest('/api/question-sets/import', { method: 'POST', body })
}
