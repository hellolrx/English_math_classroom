<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getStudentGrades, getStudentQuestionSets } from '../api/client'

const router = useRouter()
const grades = ref([])
const selectedGrade = ref('')
const sets = ref([])
const code = ref('')
const loading = ref(true)
const errorMessage = ref('')
const selectedGradeName = computed(() => grades.value.find(item => item.id === selectedGrade.value)?.name || '')

async function selectGrade(id) {
  selectedGrade.value = id
  try { sets.value = await getStudentQuestionSets(id) } catch (error) { errorMessage.value = error.message }
}
async function load() {
  try {
    grades.value = await getStudentGrades()
    if (grades.value.length) await selectGrade(grades.value[0].id)
  } catch (error) { errorMessage.value = error.message } finally { loading.value = false }
}
function enterCode() {
  if (code.value.trim()) router.push(`/student/practice/${encodeURIComponent(code.value.trim())}`)
}
onMounted(load)
</script>

<template>
  <main class="app-shell student-home-shell">
    <header class="topbar"><div><p class="eyebrow">STUDENT WORKBENCH</p><h1>學生練習</h1><p class="muted">選擇年級開始刷題，或輸入老師提供的練習碼。</p></div><button class="secondary-button" @click="router.push('/login')">登出</button></header>
    <p v-if="loading" class="loading-state">正在讀取題目…</p>
    <p v-else-if="errorMessage" class="error-message">{{ errorMessage }}</p>
    <template v-else>
      <section class="student-tool-panel"><div><h2>老師指定練習</h2><p class="muted">輸入練習碼後直接開始作答。</p></div><form class="code-form" @submit.prevent="enterCode"><input v-model="code" placeholder="輸入練習碼" /><button class="primary-button" type="submit">開始</button></form></section>
      <section class="student-tool-panel review-entry"><div><h2>記憶複習</h2><p class="muted">用「忘記／模糊／清楚記得」安排下一次複習。</p></div><button class="secondary-button" @click="router.push('/student/review')">開始複習</button></section>
      <section class="student-grade-section"><h2>按年級刷題</h2><div class="grade-card-grid"><button v-for="grade in grades" :key="grade.id" class="grade-card" :class="{ active: selectedGrade === grade.id }" @click="selectGrade(grade.id)"><strong>{{ grade.name }}</strong><small>{{ grade.question_set_count || 0 }} 組題目</small></button></div></section>
      <section class="student-set-section"><div class="panel-heading"><div><p class="eyebrow">{{ selectedGradeName }}</p><h2>題目集合</h2></div></div><p v-if="!sets.length" class="empty-state">這個年級目前沒有可用題目。</p><div v-else class="student-set-grid"><button v-for="item in sets" :key="item.id" class="student-set-card" @click="router.push(`/student/question-sets/${item.id}`)"><strong>{{ item.name }}</strong><span>{{ item.question_count }} 題</span></button></div></section>
    </template>
  </main>
</template>
