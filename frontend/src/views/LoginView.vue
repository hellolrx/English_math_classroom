<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { login } from '../api/client'

const router = useRouter()
const username = ref('admin')
const password = ref('admin123')
const loading = ref(false)
const errorMessage = ref('')

async function submit() {
  errorMessage.value = ''
  if (!username.value.trim() || !password.value) {
    errorMessage.value = '請輸入帳號及密碼'
    return
  }

  loading.value = true
  try {
    const result = await login(username.value.trim(), password.value)
    localStorage.setItem('hhx_access_token', result.access_token)
    router.push('/teacher')
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
      <h1>老師登入</h1>
      <p class="muted">管理題目、課堂答題及班級統計</p>

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
          {{ loading ? '登入中…' : '登入老師端' }}
        </button>
      </form>

      <div class="auth-footer">
        <span>學生？</span>
        <RouterLink to="/student/join">學生入口（課堂／練習碼）</RouterLink>
      </div>
    </section>
  </main>
</template>
