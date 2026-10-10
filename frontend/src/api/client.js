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
      const detail = typeof payload.detail === 'string'
        ? payload.detail
        : payload.detail?.errors?.join('\n') || payload.detail?.message || payload.message
      lastError = new Error(detail || '請求失敗，請稍後再試')
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

export async function getCurrentStudent() {
  return apiRequest('/api/student/me')
}

export async function logoutStudent() {
  return apiRequest('/api/student/logout', { method: 'POST' })
}

export async function getStudentTopics() {
  return apiRequest('/api/student/topics')
}

export async function startStudentRound(context) {
  return apiRequest('/api/student/rounds/start', { method: 'POST', body: JSON.stringify(context) })
}

export async function saveStudentRoundAnswer(payload) {
  return apiRequest('/api/student/rounds/answer', { method: 'POST', body: JSON.stringify(payload) })
}

export async function finishStudentRound(payload) {
  return apiRequest('/api/student/rounds/finish', { method: 'POST', body: JSON.stringify(payload) })
}

export async function getTeacherTopics() {
  return apiRequest('/api/teacher/topics')
}

export async function getTeacherTopic(id) {
  return apiRequest(`/api/teacher/topics/${encodeURIComponent(id)}`)
}
export async function searchTeacherQuestions(year) {
  const query = year?.trim() ? `?year=${encodeURIComponent(year.trim())}` : ''
  return apiRequest(`/api/teacher/questions${query}`)
}

export async function previewTopicImport(topicId, file) {
  const body = new FormData()
  body.append('topic_id', topicId)
  body.append('file', file)
  return apiRequest('/api/teacher/topics/preview', { method: 'POST', body })
}

export async function importTopic(topicId, file) {
  const body = new FormData()
  body.append('topic_id', topicId)
  body.append('file', file)
  return apiRequest('/api/teacher/topics/import', { method: 'POST', body })
}

export async function getClassroom(token) { return apiRequest(`/api/classroom/${encodeURIComponent(token)}`) }
export async function joinClassroom(token) { return apiRequest(`/api/classroom/${encodeURIComponent(token)}/join`, { method: 'POST' }) }
export async function answerClassroom(token, payload) { return apiRequest(`/api/classroom/${encodeURIComponent(token)}/answer`, { method: 'POST', body: JSON.stringify(payload) }) }
export async function startTeacherClassroom(id) { return apiRequest(`/api/teacher/classrooms/${id}/start`, { method: 'POST' }) }
export async function nextTeacherClassroom(id) { return apiRequest(`/api/teacher/classrooms/${id}/next`, { method: 'POST' }) }
export async function getTeacherClassroomStats(id) { return apiRequest(`/api/teacher/classrooms/${id}/stats`) }
export async function getStudentWords(gradeId) { return apiRequest(`/api/student/words?grade_id=${encodeURIComponent(gradeId)}`) }
export async function getStudentWordReview(gradeId) { return apiRequest(`/api/student/words/review?grade_id=${encodeURIComponent(gradeId)}`) }
export async function rateStudentWord(payload) { return apiRequest('/api/student/words/rate', { method: 'POST', body: JSON.stringify(payload) }) }
export async function importWords(gradeId, file) { const body = new FormData(); body.append('grade_id', gradeId); body.append('file', file); return apiRequest('/api/teacher/words/import', { method: 'POST', body }) }
export async function getTeacherWords() { return apiRequest('/api/teacher/words') }
export async function getTeacherReports() { return apiRequest('/api/teacher/reports') }
export async function getTeacherReport(kind, id) { return apiRequest(`/api/teacher/reports/${kind}/${id}`) }
export async function getTeacherPracticeSummary(classId, batchId) { return apiRequest(`/api/teacher/reports/practice-summary?class_id=${encodeURIComponent(classId)}&batch_id=${encodeURIComponent(batchId)}`) }

export async function getCurrentTeacher() {
  return apiRequest('/api/auth/me')
}

export async function getTeacherGrades() { return apiRequest('/api/teacher/grades') }
export async function getClasses() { return apiRequest('/api/teacher/classes') }

export async function createSession(payload) {
  return apiRequest('/api/sessions', { method: 'POST', body: JSON.stringify(payload) })
}
