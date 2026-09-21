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

export async function publishQuestionSet(id) {
  return apiRequest(`/api/question-sets/${id}/publish`, { method: 'POST' })
}

export async function getClasses() {
  return apiRequest('/api/classes')
}

export async function getSessions() {
  return apiRequest('/api/sessions')
}

export async function createSession(payload) {
  return apiRequest('/api/sessions', { method: 'POST', body: JSON.stringify(payload) })
}

export async function startSession(id) {
  return apiRequest(`/api/sessions/${id}/start`, { method: 'POST' })
}

export async function lockSession(id) {
  return apiRequest(`/api/sessions/${id}/lock`, { method: 'POST' })
}

export async function nextSession(id) {
  return apiRequest(`/api/sessions/${id}/next`, { method: 'POST' })
}

export async function getSessionStats(id) {
  return apiRequest(`/api/sessions/${id}/stats`)
}

export async function getSessionReport(id) {
  return apiRequest(`/api/sessions/${id}/report`)
}

export async function getPublicSession(token) {
  return apiRequest(`/api/public/sessions/${encodeURIComponent(token)}`)
}

export async function joinPublicSession(token, browserKey) {
  return apiRequest(`/api/public/sessions/${encodeURIComponent(token)}/join`, {
    method: 'POST',
    body: JSON.stringify({ browser_key: browserKey }),
  })
}

export async function submitPublicAnswer(token, payload) {
  return apiRequest(`/api/public/sessions/${encodeURIComponent(token)}/answers`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
