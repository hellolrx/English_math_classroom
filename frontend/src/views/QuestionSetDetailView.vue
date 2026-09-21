<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getQuestionSet, publishQuestionSet } from '../api/client'

const route = useRoute()
const questionSet = ref(null)
const loading = ref(true)
const errorMessage = ref('')
const publishing = ref(false)
async function publish() {
  publishing.value = true
  errorMessage.value = ''
  try { questionSet.value = await publishQuestionSet(route.params.id); questionSet.value = await getQuestionSet(route.params.id) } catch (error) { errorMessage.value = error.message } finally { publishing.value = false }
}

function formatDate(value) {
  if (!value) return '未提供日期'
  return new Intl.DateTimeFormat('zh-HK', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

onMounted(async () => {
  try {
    questionSet.value = await getQuestionSet(route.params.id)
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="app-shell">
    <header class="topbar">
      <div>
        <RouterLink class="back-link-inline" to="/teacher/question-sets">← 返回題目集合</RouterLink>
        <p class="eyebrow">QUESTION SET DETAIL</p>
        <h1>{{ questionSet?.name || '題目集合' }}</h1>
        <p v-if="questionSet" class="muted">建立時間：{{ formatDate(questionSet.created_at) }} · {{ questionSet.questions.length }} 題</p>
      </div>
    </header>

    <p v-if="loading" class="loading-state">正在讀取題目…</p>
    <p v-else-if="errorMessage" class="error-message">{{ errorMessage }}</p>
    <section v-else class="detail-panel">
      <article v-for="question in questionSet.questions" :key="question.id" class="question-preview-card">
        <div class="question-number">{{ question.sort_order }}</div>
        <div class="question-preview-body">
          <h3>{{ question.question_text || '圖片題目' }}</h3>
          <div class="option-preview-grid">
            <span v-for="option in question.options" :key="option.id" :class="{ correct: option.id === question.correct_option_id }">
              {{ option.option_key }}. {{ option.option_text || '圖片選項' }}
            </span>
          </div>
          <p v-if="question.explanation" class="helper-text">解析：{{ question.explanation }}</p>
        </div>
      </article>
      <div class="button-row session-actions">
        <button v-if="questionSet.status === 'draft'" class="primary-button" :disabled="publishing" @click="publish">{{ publishing ? '发布中…' : '发布题目集合' }}</button>
        <RouterLink v-if="questionSet.status === 'published'" class="primary-button inline-button" :to="`/teacher/sessions/new?questionSetId=${questionSet.id}`">建立课堂场次</RouterLink>
      </div>
    </section>
  </main>
</template>
