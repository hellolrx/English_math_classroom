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
  <main class="auth-shell ui-v2-shell">
    <a-card class="auth-card ui-v2-card" :bordered="false">
      <div class="brand-mark">數</div>
      <p class="eyebrow">ENGLISH MATH CLASSROOM</p>
      <h1>老師登入</h1>
      <p class="muted">管理題目、課堂答題及班級統計</p>

      <form class="form-stack" @submit.prevent="submit">
        <a-form-item field="username" label="帳號">
          <a-input v-model="username" autocomplete="username" placeholder="請輸入帳號" />
        </a-form-item>
        <a-form-item field="password" label="密碼">
          <a-input-password v-model="password" autocomplete="current-password" placeholder="請輸入密碼" />
        </a-form-item>
        <a-alert v-if="errorMessage" type="error" show-icon role="alert">{{ errorMessage }}</a-alert>
        <a-button type="primary" html-type="submit" long :loading="loading">登入老師端</a-button>
      </form>

      <div class="auth-footer">
        <span>學生？</span>
        <RouterLink to="/student/join">學生入口（課堂／練習碼）</RouterLink>
      </div>
    </a-card>
  </main>
</template>
