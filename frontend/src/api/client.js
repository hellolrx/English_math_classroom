const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export async function apiRequest(path, options = {}) {
  const headers = new Headers(options.headers || {})
  headers.set('Accept', 'application/json')
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const token = localStorage.getItem('hhx_mode') === 'student'
    ? localStorage.getItem('hhx_student_token')
    : localStorage.getItem('hhx_access_token')
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const canRetry = (options.method || 'GET').toUpperCase() === 'GET'
  let lastError
  for (let attempt = 0; attempt < (canRetry ? 3 : 1); attempt += 1) {
    try {
      const response = await fetch(`${apiBaseUrl}${path}`, { ...options, headers })
      const payload = await response.json().catch(() => ({}))
      if (response.ok) return payload
      lastError = new Error(payload.detail || payload.message || '請求失敗，請稍後再試')
      if (!canRetry || response.status < 500 || attempt === 2) throw lastError
    } catch (error) {
      lastError = error
      if (!canRetry || attempt === 2) throw error
    }
    await new Promise(resolve => setTimeout(resolve, 350 * (attempt + 1)))
  }
  throw lastError || new Error('請求失敗，請稍後再試')
}

export async function login(username, password, mode = 'teacher') {
  return apiRequest('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password, mode }),
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

export async function importQuestionSet(name, file, gradeId = '') {
  const body = new FormData()
  body.append('name', name)
  if (gradeId) body.append('grade_id', gradeId)
  body.append('file', file)
  return apiRequest('/api/question-sets/import', { method: 'POST', body })
}

export async function publishQuestionSet(id) {
  return apiRequest(`/api/question-sets/${id}/publish`, { method: 'POST' })
}

export async function archiveQuestionSet(id) {
  return apiRequest(`/api/question-sets/${id}/archive`, { method: 'POST' })
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

export async function nextSession(id) {
  return apiRequest(`/api/sessions/${id}/next`, { method: 'POST' })
}

export async function previousSession(id) {
  return apiRequest(`/api/sessions/${id}/previous`, { method: 'POST' })
}

export async function getSessionStats(id) {
  return apiRequest(`/api/sessions/${id}/stats`)
}

export async function getSessionReport(id) {
  return apiRequest(`/api/sessions/${id}/report`)
}

export async function archiveSession(id) {
  return apiRequest(`/api/sessions/${id}/archive`, { method: 'POST' })
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

export async function getPublicPractice(code) {
  return apiRequest(`/api/public/practice/${encodeURIComponent(code)}`)
}

export async function startPublicPractice(code, browserKey) {
  return apiRequest(`/api/public/practice/${encodeURIComponent(code)}/start`, {
    method: 'POST',
    body: JSON.stringify({ browser_key: browserKey }),
  })
}

export async function submitPracticeAnswer(code, payload) {
  return apiRequest(`/api/public/practice/${encodeURIComponent(code)}/answers`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function completePublicPractice(code, payload) {
  return apiRequest(`/api/public/practice/${encodeURIComponent(code)}/complete`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getStudentGrades() {
  return apiRequest('/api/student/grades')
}

export async function getStudentQuestionSets(gradeId) {
  const query = gradeId ? `?grade_id=${encodeURIComponent(gradeId)}` : ''
  return apiRequest(`/api/student/question-sets${query}`)
}

export async function getStudentQuestionSet(id) {
  return apiRequest(`/api/student/question-sets/${encodeURIComponent(id)}`)
}

export async function startStudentPractice(id, browserKey) {
  return apiRequest(`/api/student/question-sets/${encodeURIComponent(id)}/start`, { method: 'POST', body: JSON.stringify({ browser_key: browserKey }) })
}

export async function submitStudentPracticeAnswer(id, payload) {
  return apiRequest(`/api/student/question-sets/${encodeURIComponent(id)}/answers`, { method: 'POST', body: JSON.stringify(payload) })
}

export async function completeStudentPractice(id, payload) {
  return apiRequest(`/api/student/question-sets/${encodeURIComponent(id)}/complete`, { method: 'POST', body: JSON.stringify(payload) })
}

export async function getStudentReview(gradeId, browserKey) {
  const params = new URLSearchParams({ browser_key: browserKey })
  if (gradeId) params.set('grade_id', gradeId)
  return apiRequest(`/api/student/review?${params.toString()}`)
}

export async function submitStudentReviewAnswer(payload) {
  return apiRequest('/api/student/review/answer', { method: 'POST', body: JSON.stringify(payload) })
}

export async function checkStudentReviewAnswer(payload) {
  return apiRequest('/api/student/review/check', { method: 'POST', body: JSON.stringify({ ...payload, rating: 'fuzzy' }) })
}
