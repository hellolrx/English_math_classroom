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
// The deployed test environment uses the seeded hhx003 account for smoke tests.
const allowTestPrefill = true

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
  <main class="auth-shell" :class="{ 'student-ui student-login': mode === 'student' }">
    <div :class="mode === 'student' ? 'student-login-layout' : 'teacher-login-layout'">
    <div v-if="mode === 'student'" class="student-login-intro">
      <p class="eyebrow">A LITTLE PRACTICE, EVERY DAY</p>
      <h2>每天學一點，<br />慢慢進步。</h2>
      <p>從一個單詞、一道題目開始，<br />找到自己的學習節奏。</p>
      <svg class="student-login-art" viewBox="0 0 320 220" fill="none" aria-hidden="true">
        <circle cx="157" cy="110" r="94" fill="#e0f2fe" />
        <rect x="43" y="67" width="104" height="117" rx="20" fill="#c8e6a9" transform="rotate(-10 43 67)" />
        <rect x="47" y="60" width="104" height="117" rx="20" fill="#f4fce9" stroke="#91c568" stroke-width="3" transform="rotate(-10 47 60)" />
        <text x="76" y="132" fill="#438014" font-size="46" font-weight="800" transform="rotate(-10 76 132)">Aa</text>
        <rect x="161" y="61" width="112" height="127" rx="20" fill="#b3ddf1" transform="rotate(10 161 61)" />
        <rect x="163" y="53" width="112" height="127" rx="20" fill="white" stroke="#6bbce3" stroke-width="3" transform="rotate(10 163 53)" />
        <path d="M181 91l58 10M178 111l42 7M175 131l28 5" stroke="#84c9eb" stroke-width="7" stroke-linecap="round" />
        <circle cx="239" cy="152" r="22" fill="#ffc800" />
        <path d="M231 152l6 6 11-12" stroke="#795600" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
        <path d="M54 37v14M47 44h14M282 102v14M275 109h14" stroke="#91c568" stroke-width="4" stroke-linecap="round" />
        <circle cx="233" cy="28" r="7" fill="#ffc800" />
      </svg>
    </div>
    <section class="auth-card" :class="{ 'student-login-card': mode === 'student' }">
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
    </div>
  </main>
</template>

<style scoped>
.teacher-login-layout { display: contents; }
</style>
