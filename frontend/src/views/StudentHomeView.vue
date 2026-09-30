<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getStudentTopics } from '../api/client'

const router = useRouter()
const topics = ref([])
const loading = ref(true)
const errorMessage = ref('')
const code = ref('')

async function load() {
  try {
    topics.value = await getStudentTopics()
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    loading.value = false
  }
}

function enterCode() {
  if (code.value.trim()) router.push(`/student/practice/${encodeURIComponent(code.value.trim())}`)
}

onMounted(load)
</script>

<template>
  <main class="app-shell student-home-shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">STUDENT WORKBENCH</p>
        <h1>學生工作台</h1>
        <p class="muted">選擇主題開始課後練習，或進入課室答題。</p>
      </div>
      <button class="secondary-button" @click="router.push('/login')">登出</button>
    </header>
    <p v-if="loading" class="loading-state">正在讀取主題…</p>
    <p v-else-if="errorMessage" class="error-message">{{ errorMessage }}</p>
    <template v-else>
      <section class="student-tool-panel">
        <div>
          <h2>課室答題</h2>
          <p class="muted">輸入老師提供的練習碼後開始作答。</p>
        </div>
        <form class="code-form" @submit.preventDefault="enterCode">
          <input v-model="code" placeholder="輸入練習碼" />
          <button class="primary-button" type="submit">開始</button>
        </form>
      </section>
      <section class="student-tool-panel review-entry">
        <div>
          <h2>背單詞</h2>
          <p class="muted">學習和複習英語單詞。</p>
        </div>
        <button class="secondary-button" @click="router.push('/student/review')">開始學習</button>
      </section>
      <section class="student-topic-section">
        <h2>課後練習</h2>
        <p v-if="!topics.length" class="empty-state">目前沒有可用的主題。</p>
        <div v-else class="topic-grid">
          <button v-for="topic in topics" :key="topic.id" class="topic-card" @click="router.push(`/student/practice/${topic.id}`)">
            <span class="topic-code">{{ topic.code }}</span>
            <strong>{{ topic.name }}</strong>
          </button>
        </div>
      </section>
    </template>
  </main>
</template>
