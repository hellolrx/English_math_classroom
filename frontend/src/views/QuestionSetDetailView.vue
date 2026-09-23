<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getQuestionSet, publishQuestionSet, archiveQuestionSet } from '../api/client'
import { useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const questionSet = ref(null)
const loading = ref(true)
const errorMessage = ref('')
const publishing = ref(false)
const archiving = ref(false)
async function publish() {
  publishing.value = true
  errorMessage.value = ''
  try { questionSet.value = await publishQuestionSet(route.params.id); questionSet.value = await getQuestionSet(route.params.id) } catch (error) { errorMessage.value = error.message } finally { publishing.value = false }
}

async function archive() {
  if (!window.confirm('确定要归档这个题目集合吗？归档后不会删除数据，但不会再出现在默认列表中。')) return
  archiving.value = true
  errorMessage.value = ''
  try { await archiveQuestionSet(route.params.id); router.replace('/teacher/question-sets') } catch (error) { errorMessage.value = error.message } finally { archiving.value = false }
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
          <img v-if="question.question_image_url" class="question-image" :src="question.question_image_url" alt="題目圖片" />
          <h3 v-if="question.question_text">{{ question.question_text }}</h3>
          <div class="option-preview-grid">
            <span v-for="option in question.options" :key="option.id" :class="{ correct: option.id === question.correct_option_id }">
              <strong>{{ option.option_key }}.</strong>
              <img v-if="option.option_image_url" class="option-image" :src="option.option_image_url" alt="選項圖片" />
              <template v-else>{{ option.option_text }}</template>
            </span>
          </div>
          <p v-if="question.explanation" class="helper-text">解析：{{ question.explanation }}</p>
        </div>
      </article>
      <div class="button-row session-actions">
        <button v-if="questionSet.status === 'draft'" class="primary-button" :disabled="publishing" @click="publish">{{ publishing ? '发布中…' : '发布题目集合' }}</button>
        <RouterLink v-else-if="questionSet.status === 'published'" class="status-pill" to="/teacher/sessions/new">去工作台建立课堂</RouterLink>
        <span v-else class="status-pill">已归档</span>
        <button v-if="questionSet.status !== 'archived'" class="secondary-button" :disabled="archiving" @click="archive">{{ archiving ? '归档中…' : '归档题目集合' }}</button>
      </div>
    </section>
  </main>
</template>
