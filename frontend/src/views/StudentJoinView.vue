<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { getPublicSession } from '../api/client'

const router = useRouter()
const sessionCode = ref('')
const loading = ref(false)
const errorMessage = ref('')

async function enter() {
  const code = sessionCode.value.trim()
  if (!code) {
    errorMessage.value = '請輸入課堂或練習碼'
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    const session = await getPublicSession(code)
    router.push(session.session_type === 'homework' ? `/student/practice/${encodeURIComponent(code)}` : `/student/session/${encodeURIComponent(code)}`)
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="auth-shell">
    <section class="auth-card student-card">
      <div class="brand-mark student-mark">答</div>
      <p class="eyebrow">ENGLISH MATH CLASSROOM</p>
      <h1>學生入口</h1>
      <p class="muted">課堂掃描 QR Code；課後練習直接輸入練習碼。</p>
      <form class="form-stack" @submit.prevent="enter">
        <label>
          <span>課堂／練習碼</span>
          <input v-model="sessionCode" autocomplete="off" placeholder="請輸入代碼" />
        </label>
        <p v-if="errorMessage" class="error-message" role="alert">{{ errorMessage }}</p>
        <button class="primary-button" type="submit" :disabled="loading">{{ loading ? '進入中…' : '進入' }}</button>
      </form>
      <RouterLink class="back-link" to="/login">返回老師登入</RouterLink>
    </section>
  </main>
</template>
