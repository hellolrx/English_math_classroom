<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getCurrentTeacher } from '../api/client'

const router = useRouter()
const teacher = ref(null)
const loading = ref(true)
const errorMessage = ref('')

onMounted(async () => {
  try {
    teacher.value = await getCurrentTeacher()
  } catch (error) {
    errorMessage.value = error.message
    localStorage.removeItem('hhx_access_token')
    router.replace('/login')
  } finally {
    loading.value = false
  }
})

function logout() {
  localStorage.removeItem('hhx_access_token')
  router.push('/login')
}
</script>

<template>
  <main class="app-shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">ENGLISH MATH CLASSROOM</p>
        <h1>老師工作台</h1>
      </div>
      <button class="text-button" @click="logout">登出</button>
    </header>

    <p v-if="loading" class="loading-state">正在讀取老師資料…</p>
    <p v-else-if="errorMessage" class="error-message">{{ errorMessage }}</p>
    <template v-else>
      <section class="welcome-panel">
        <div>
          <p class="eyebrow">WELCOME BACK</p>
          <h2>{{ teacher?.display_name || '老師' }}</h2>
          <p class="muted">已連接到預設學校，可以開始建立題目集合。</p>
        </div>
        <span class="status-pill">帳戶正常</span>
      </section>

      <section class="feature-grid">
        <RouterLink class="feature-card feature-card-accent feature-card-link" to="/teacher/question-sets">
          <span class="feature-icon">題</span>
          <h3>題目管理</h3>
          <p>上傳 Excel、預覽題目並建立題目集合。</p>
        </RouterLink>
        <RouterLink class="feature-card feature-card-link" to="/teacher/sessions/new">
          <span class="feature-icon">課</span>
          <h3>課堂場次</h3>
          <p>建立班級答題場次，產生學生掃描用 QR Code。</p>
        </RouterLink>
        <article class="feature-card">
          <span class="feature-icon">統</span>
          <h3>即時統計</h3>
          <p>查看學生提交數量及 A、B、C、D 選項分布。</p>
        </article>
      </section>
    </template>
  </main>
</template>
