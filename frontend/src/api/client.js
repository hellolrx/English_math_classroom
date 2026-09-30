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

export async function changePassword(currentPassword, newPassword) {
  return apiRequest('/api/student/password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
}

export async function getCurrentTeacher() {
  return apiRequest('/api/auth/me')
}

// Topics (teacher)
export async function getTopics() {
  return apiRequest('/api/topics')
}

// Topics (student)
export async function getStudentTopics() {
  return apiRequest('/api/student/topics')
}

export async function getTopicQuestions(topicId) {
  return apiRequest(`/api/student/topics/${encodeURIComponent(topicId)}/questions`)
}

// Student practice
export async function getPracticeProgress(topicId) {
  return apiRequest(`/api/student/practice/${encodeURIComponent(topicId)}/progress`)
}

export async function submitPracticeAnswer(topicId, payload) {
  return apiRequest(`/api/student/practice/${encodeURIComponent(topicId)}/answer`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

// Student vocabulary
export async function getStudentVocabulary() {
  return apiRequest('/api/student/vocabulary')
}

export async function getReviewWords() {
  return apiRequest('/api/student/vocabulary/review')
}

export async function rateWord(payload) {
  return apiRequest('/api/student/vocabulary/rate', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

// Student grades
export async function getStudentGrades() {
  return apiRequest('/api/student/grades')
}

// Question sets (teacher)
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

// Vocabulary (teacher)
export async function getVocabularyByGrade(gradeId) {
  return apiRequest(`/api/vocabulary/${encodeURIComponent(gradeId)}`)
}

export async function previewVocabulary(file) {
  const body = new FormData()
  body.append('file', file)
  return apiRequest('/api/vocabulary/preview', { method: 'POST', body })
}

export async function importVocabulary(file, gradeId) {
  const body = new FormData()
  body.append('file', file)
  body.append('grade_id', gradeId)
  return apiRequest('/api/vocabulary/import', { method: 'POST', body })
}

// Classes
export async function getClasses() {
  return apiRequest('/api/classes')
}

// Sessions (teacher)
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

// Public session (student)
export async function getPublicSession(token) {
  return apiRequest(`/api/public/sessions/${encodeURIComponent(token)}`)
}

export async function joinPublicSession(token) {
  return apiRequest(`/api/public/sessions/${encodeURIComponent(token)}/join`, {
    method: 'POST',
  })
}

export async function submitPublicAnswer(token, payload) {
  return apiRequest(`/api/public/sessions/${encodeURIComponent(token)}/answers`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
