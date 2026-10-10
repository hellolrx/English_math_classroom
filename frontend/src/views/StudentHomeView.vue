<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getCurrentStudent, getStudentTopics, logoutStudent } from '../api/client'

const router = useRouter()
const student = ref(null)
const topics = ref([])
const code = ref('')
const loading = ref(true)
const signingOut = ref(false)
const errorMessage = ref('')
const topicsError = ref('')

async function load() {
  try {
    student.value = await getCurrentStudent()
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    loading.value = false
  }
  if (student.value?.grade === 'S6') {
    try {
      topics.value = await getStudentTopics()
    } catch (error) {
      topicsError.value = error.message
    }
  }
}

async function signOut() {
  signingOut.value = true
  try { await logoutStudent() } catch { /* Clear the local credential even if the network is unavailable. */ }
  localStorage.removeItem('hhx_student_token')
  localStorage.removeItem('hhx_student_profile')
  localStorage.removeItem('hhx_mode')
  router.replace('/login')
}

function enterCode() {
  const value = code.value.trim()
  if (value) router.push(`/student/practice/${encodeURIComponent(value)}`)
}

onMounted(load)
</script>

<template>
  <main class="app-shell student-home-shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">STUDENT WORKBENCH</p>
        <h1>{{ student?.display_name || '學生練習' }}</h1>
        <p class="muted">{{ student?.student_number }} · {{ student?.grade }} · {{ student?.class_name }}</p>
      </div>
      <button class="secondary-button" :disabled="signingOut" @click="signOut">登出</button>
    </header>
    <p v-if="loading" class="loading-state">正在讀取學習內容…</p>
    <p v-else-if="errorMessage" class="error-message" role="alert">{{ errorMessage }}</p>
    <template v-else>
      <section class="student-tool-panel">
        <div><h2>老師指定練習</h2><p class="muted">輸入練習碼進入整份指定題目。</p></div>
        <form class="code-form" @submit.prevent="enterCode">
          <input v-model="code" autocomplete="off" placeholder="輸入練習碼" />
          <button class="primary-button" type="submit" :disabled="!code.trim()">開始</button>
        </form>
      </section>
      <section class="student-tool-panel"><div><h2>单词学习</h2><p class="muted">按年级查看单词，翻卡后选择记忆程度。</p></div><RouterLink class="primary-button" to="/student/words">开始学习</RouterLink></section>
      <section v-if="student?.grade === 'S6'" class="student-set-section">
        <div class="panel-heading"><div><p class="eyebrow">S6</p><h2>數學主題</h2></div></div>
        <p v-if="topicsError" class="error-message" role="alert">數學主題讀取失敗：{{ topicsError }}</p>
        <p v-else-if="!topics.length" class="empty-state">目前沒有可用主題。</p>
        <div v-else class="student-set-grid">
          <button v-for="topic in topics" :key="topic.id" class="student-set-card"
            :disabled="!topic.batch_id" @click="router.push(`/student/topics/${topic.id}`)">
            <strong>{{ topic.code }} · {{ topic.name }}</strong>
            <span>{{ topic.batch_id ? `${topic.question_count} 題` : '暫無題目' }}</span>
          </button>
        </div>
      </section>
    </template>
  </main>
</template>
