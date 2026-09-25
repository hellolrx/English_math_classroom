<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { login } from '../api/client'

const router = useRouter()
const username = ref('admin')
const password = ref('admin123')
const loading = ref(false)
const errorMessage = ref('')
const mode = ref('teacher')

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
      router.push('/student')
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
          <span>帳號</span>
          <input v-model="username" autocomplete="username" placeholder="請輸入帳號" />
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
        <button class="link-button" type="button" @click="mode = mode === 'teacher' ? 'student' : 'teacher'; errorMessage = ''">
          {{ mode === 'teacher' ? '切換學生登入' : '切換老師登入' }}
        </button>
      </div>
    </section>
  </main>
</template>
