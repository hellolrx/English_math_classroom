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
  <main class="app-shell ui-v2-shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">ENGLISH MATH CLASSROOM</p>
        <h1>老師工作台</h1>
      </div>
      <a-button status="danger" type="text" @click="logout">登出</a-button>
    </header>

    <a-skeleton v-if="loading" :animation="true" :rows="4" />
    <a-alert v-else-if="errorMessage" type="error" show-icon>{{ errorMessage }}</a-alert>
    <template v-else>
      <a-card class="welcome-panel ui-v2-card" :bordered="false">
        <div>
          <p class="eyebrow">WELCOME BACK</p>
          <h2>{{ teacher?.display_name || '老師' }}</h2>
          <p class="muted">已連接到預設學校，可以開始建立題目集合。</p>
        </div>
        <a-tag color="green">帳戶正常</a-tag>
      </a-card>

      <section class="feature-grid">
        <RouterLink class="feature-card feature-card-accent feature-card-link ui-v2-card" to="/teacher/question-sets">
          <span class="feature-icon">題</span>
          <h3>題目管理</h3>
          <p>上傳 Excel、預覽題目並建立題目集合。</p>
        </RouterLink>
        <RouterLink class="feature-card feature-card-link ui-v2-card" to="/teacher/sessions/new">
          <span class="feature-icon">課</span>
          <h3>課堂／課後</h3>
          <p>建立課堂 QR Code 或課後練習碼。</p>
        </RouterLink>
        <RouterLink class="feature-card feature-card-link ui-v2-card" to="/teacher/reports">
          <span class="feature-icon">統</span>
          <h3>習題統計</h3>
          <p>查看即時課堂及課後練習的作答分布。</p>
        </RouterLink>
      </section>
    </template>
  </main>
</template>
