<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { completePublicPractice, getPublicPractice, startPublicPractice, submitPracticeAnswer } from '../api/client'

const route = useRoute()
const router = useRouter()
const code = route.params.code
const practice = ref(null)
const attemptId = ref('')
const index = ref(0)
const selected = ref('')
const loading = ref(true)
const submitting = ref(false)
const errorMessage = ref('')
const result = ref(null)

const browserKey = (() => {
  const key = localStorage.getItem('hhx_browser_key')
  if (key) return key
  const next = crypto.randomUUID()
  localStorage.setItem('hhx_browser_key', next)
  return next
})()

const question = computed(() => practice.value?.questions?.[index.value] || null)
const isLast = computed(() => Boolean(practice.value && index.value === practice.value.questions.length - 1))
const answeredCount = computed(() => result.value?.answers?.length || index.value + (selected.value ? 1 : 0))

async function load() {
  try {
    practice.value = await getPublicPractice(code)
    const started = await startPublicPractice(code, browserKey)
    attemptId.value = started.attempt_id
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    loading.value = false
  }
}

async function choose(option) {
  if (!question.value || submitting.value || selected.value === option.id) return
  submitting.value = true
  errorMessage.value = ''
  try {
    await submitPracticeAnswer(code, {
      browser_key: browserKey,
      attempt_id: attemptId.value,
      question_id: question.value.id,
      selected_option_id: option.id,
    })
    selected.value = option.id
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    submitting.value = false
  }
}

async function next() {
  if (!selected.value || submitting.value) return
  submitting.value = true
  errorMessage.value = ''
  try {
    if (isLast.value) {
      result.value = await completePublicPractice(code, { browser_key: browserKey, attempt_id: attemptId.value })
    } else {
      index.value += 1
      selected.value = ''
    }
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    submitting.value = false
  }
}

function restart() {
  router.replace('/student/join')
}

onMounted(load)
</script>

<template>
  <main class="auth-shell">
    <section class="auth-card student-card student-session-card">
      <div class="brand-mark student-mark">答</div>
      <p class="eyebrow">ENGLISH MATH CLASSROOM</p>
      <h1>課後練習</h1>

      <p v-if="loading" class="loading-state">正在載入練習…</p>
      <p v-else-if="errorMessage" class="error-message" role="alert">{{ errorMessage }}</p>
      <template v-else-if="result">
        <div class="completion-message">
          <h2>練習已完成</h2>
          <p>你已完成全部 {{ practice.questions.length }} 題，可以查看本次結果。</p>
        </div>
        <div class="practice-result-list">
          <div v-for="(answer, answerIndex) in result.answers" :key="answer.question_id" class="practice-result-row">
            <span>第 {{ answerIndex + 1 }} 題</span>
            <strong :class="answer.is_correct ? 'result-correct' : 'result-wrong'">{{ answer.is_correct ? '答對' : '答錯' }}</strong>
          </div>
        </div>
        <button class="secondary-button practice-back-button" @click="restart">返回學生入口</button>
      </template>
      <template v-else-if="question">
        <div class="practice-progress"><span>第 {{ index + 1 }} / {{ practice.questions.length }} 題</span><span>已作答 {{ answeredCount }} 題</span></div>
        <img v-if="question.question_image_url" class="question-image" :src="question.question_image_url" alt="題目圖片" />
        <h2 v-if="question.question_text" class="student-question">{{ question.question_text }}</h2>
        <div class="student-options">
          <button v-for="option in question.options" :key="option.id" :class="{ selected: selected === option.id }" :disabled="submitting" @click="choose(option)">
            <strong>{{ option.option_key }}.</strong><img v-if="option.option_image_url" class="option-image" :src="option.option_image_url" alt="選項圖片" /><template v-else>{{ option.option_text }}</template>
          </button>
        </div>
        <p v-if="errorMessage" class="error-message" role="alert">{{ errorMessage }}</p>
        <p :class="selected ? 'success-message' : 'pending-message'">{{ selected ? '答案已提交' : '請選擇答案' }}</p>
        <button class="primary-button practice-next-button" :disabled="!selected || submitting" @click="next">{{ submitting ? '處理中…' : (isLast ? '完成練習' : '下一題') }}</button>
      </template>
    </section>
  </main>
</template>
