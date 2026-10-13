<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login } from '../api/client'

const router = useRouter()
const route = useRoute()
const studentEntry = route.query.mode === 'student' || (typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/student/'))
const username = ref(studentEntry ? 'hhx003' : 'admin')
const password = ref(studentEntry ? '123' : 'admin123')
const loading = ref(false)
const errorMessage = ref('')
const mode = ref(studentEntry ? 'student' : 'teacher')
// The deployed test environment uses the seeded hhx003 account for smoke tests.
const allowTestPrefill = true

function switchMode() {
  if (loading.value) return
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
    if (mode.value === 'student') {
      localStorage.setItem('hhx_student_token', result.student_token)
      localStorage.removeItem('hhx_student_profile')
      const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/student/')
        ? route.query.redirect
        : '/student'
      router.push(redirect)
    } else {
      localStorage.setItem('hhx_access_token', result.access_token)
      const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/teacher/')
        ? route.query.redirect : '/teacher'
      router.push(redirect)
    }
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="auth-shell student-ui student-login" :class="{ 'teacher-ui teacher-login': mode === 'teacher' }">
    <div class="student-login-layout">
    <div class="student-login-intro">
      <p class="eyebrow">{{ mode === 'teacher' ? 'MAKE EVERY LESSON COUNT' : 'A LITTLE PRACTICE, EVERY DAY' }}</p>
      <h2 v-if="mode === 'teacher'">讓每一道題，<br />連起整個課堂。</h2>
      <h2 v-else>每天學一點，<br />慢慢進步。</h2>
      <p v-if="mode === 'teacher'">準備題目、邀請學生，<br />一起看見學習的進步。</p>
      <p v-else>從一個單詞、一道題目開始，<br />找到自己的學習節奏。</p>
      <svg v-if="mode === 'teacher'" class="student-login-art" viewBox="0 0 320 220" fill="none" aria-hidden="true">
        <circle cx="160" cy="110" r="94" fill="#eee7fc" />
        <rect x="43" y="39" width="234" height="139" rx="20" fill="#d4c5eb" />
        <rect x="43" y="33" width="234" height="139" rx="20" fill="white" stroke="#b398d7" stroke-width="3" />
        <rect x="60" y="50" width="200" height="96" rx="12" fill="#f6f1fc" />
        <text x="82" y="111" fill="#7652a0" font-size="38" font-weight="800">x + y</text>
        <path d="M117 196h86M144 175v21M176 175v21" stroke="#b398d7" stroke-width="6" stroke-linecap="round" />
        <circle cx="239" cy="153" r="23" fill="#ffdb9b" />
        <path d="M229 153l7 7 13-14" stroke="#996011" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
        <path d="M34 28v14M27 35h14M287 98v14M280 105h14" stroke="#96caa3" stroke-width="4" stroke-linecap="round" />
      </svg>
      <svg v-else class="student-login-art" viewBox="0 0 320 220" fill="none" aria-hidden="true">
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
    <section class="auth-card student-login-card">
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
        <button class="link-button" type="button" :disabled="loading" @click="switchMode">
          {{ mode === 'teacher' ? '切換學生登入' : '切換老師登入' }}
        </button>
      </div>
    </section>
    </div>
  </main>
</template>
