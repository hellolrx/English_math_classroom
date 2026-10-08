<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login } from '../api/client'

const router = useRouter()
const route = useRoute()
const username = ref('admin')
const password = ref('admin123')
const loading = ref(false)
const errorMessage = ref('')
const mode = ref('teacher')
const allowTestPrefill = import.meta.env.DEV || import.meta.env.VITE_ENABLE_TEST_CREDENTIAL_PREFILL === 'true'

function switchMode() {
  mode.value = mode.value === 'teacher' ? 'student' : 'teacher'
  username.value = mode.value === 'student' ? (allowTestPrefill ? 'hhx003' : '') : 'admin'
  password.value = mode.value === 'student' ? (allowTestPrefill ? '123' : '') : 'admin123'
  errorMessage.value = ''
}

async function submit() {
  errorMessage.value = ''
  if (!username.value.trim() || !password.value) {
    errorMessage.value = '請輸入帳號及密碼'
    return
  }

  loading.value = true
  try {
    const result = await login(username.value.trim(), password.value, mode.value)
    localStorage.removeItem('hhx_access_token')
    localStorage.removeItem('hhx_student_token')
    if (mode.value === 'student') {
      localStorage.setItem('hhx_student_token', result.student_token)
      localStorage.setItem('hhx_mode', 'student')
      const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/student/')
        ? route.query.redirect
        : '/student'
      router.push(redirect)
    } else {
      localStorage.setItem('hhx_access_token', result.access_token)
      localStorage.setItem('hhx_mode', 'teacher')
      router.push('/teacher')
    }
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="auth-shell">
    <section class="auth-card">
      <div class="brand-mark">數</div>
      <p class="eyebrow">ENGLISH MATH CLASSROOM</p>
      <h1>{{ mode === 'teacher' ? '老師登入' : '學生登入' }}</h1>
      <p class="muted">{{ mode === 'teacher' ? '管理題目、課堂答題及班級統計' : '選擇年級、刷題及進行記憶複習' }}</p>

      <form class="form-stack" @submit.prevent="submit">
        <label>
          <span>{{ mode === 'student' ? '學號' : '老師帳號' }}</span>
          <input v-model="username" autocomplete="username" :placeholder="mode === 'student' ? '請輸入學號' : '請輸入老師帳號'" />
        </label>
        <label>
          <span>密碼</span>
          <input v-model="password" type="password" autocomplete="current-password" placeholder="請輸入密碼" />
        </label>
        <p v-if="errorMessage" class="error-message" role="alert">{{ errorMessage }}</p>
        <button class="primary-button" type="submit" :disabled="loading">
          {{ loading ? '登入中…' : (mode === 'teacher' ? '登入老師端' : '登入學生端') }}
        </button>
      </form>

      <div class="auth-footer">
        <span>{{ mode === 'teacher' ? '學生？' : '老師？' }}</span>
        <button class="link-button" type="button" @click="switchMode">
          {{ mode === 'teacher' ? '切換學生登入' : '切換老師登入' }}
        </button>
      </div>
    </section>
  </main>
</template>
