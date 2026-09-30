<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getTopicQuestions, getPracticeProgress, submitPracticeAnswer } from '../api/client'

const route = useRoute()
const router = useRouter()
const topicId = route.params.code
const questions = ref([])
const progress = ref(null)
const index = ref(0)
const selected = ref('')
const answerText = ref('')
const loading = ref(true)
const submitting = ref(false)
const errorMessage = ref('')
const answeredCount = ref(0)
const currentResult = ref(null)

const question = computed(() => questions.value[index.value] || null)
const isLast = computed(() => Boolean(questions.value.length && index.value === questions.value.length - 1))

async function load() {
  try {
    questions.value = await getTopicQuestions(topicId)
    progress.value = await getPracticeProgress(topicId)
    if (progress.value?.current_question_order) {
      index.value = Math.max(0, progress.value.current_question_order - 1)
    }
    answeredCount.value = progress.value?.answered_count || 0
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    loading.value = false
  }
}

async function choose(option) {
  if (!question.value || submitting.value || selected.value === option.option_key) return
  submitting.value = true
  errorMessage.value = ''
  try {
    const result = await submitPracticeAnswer(topicId, {
      question_id: question.value.id,
      answer_type: 'single_choice',
      selected_option_id: option.option_key,
    })
    selected.value = option.option_key
    currentResult.value = result
    answeredCount.value += 1
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    submitting.value = false
  }
}

async function submitTextAnswer() {
  if (!question.value || submitting.value || !answerText.value.trim()) return
  submitting.value = true
  errorMessage.value = ''
  try {
    await submitPracticeAnswer(topicId, {
      question_id: question.value.id,
      answer_type: 'text_input',
      answer_text: answerText.value.trim(),
    })
    currentResult.value = { submitted: true }
    answeredCount.value += 1
    answerText.value = ''
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    submitting.value = false
  }
}

function next() {
  if (!selected.value && !currentResult.value?.submitted) return
  if (isLast.value) {
    router.push('/student')
  } else {
    index.value += 1
    selected.value = ''
    currentResult.value = null
  }
}

function previous() {
  if (index.value > 0) {
    index.value -= 1
    selected.value = ''
    currentResult.value = null
  }
}

function restart() {
  router.push('/student')
}

onMounted(load)
</script>

<template>
  <main class="auth-shell">
    <section class="auth-card student-card student-session-card">
      <div class="brand-mark student-mark">練</div>
      <p class="eyebrow">ENGLISH MATH CLASSROOM</p>
      <h1>課後練習</h1>

      <p v-if="loading" class="loading-state">正在載入練習…</p>
      <p v-else-if="errorMessage" class="error-message" role="alert">{{ errorMessage }}</p>
      <template v-else-if="question">
        <div class="practice-progress">
          <span>第 {{ index + 1 }} / {{ questions.length }} 題</span>
          <span>已作答 {{ answeredCount }} 題</span>
        </div>
        
        <!-- Single choice question -->
        <template v-if="question.question_type === 'single_choice' || !question.question_type">
          <img v-if="question.question_image_url" class="question-image" :src="question.question_image_url" alt="題目圖片" />
          <h2 v-if="question.question_text" class="student-question">{{ question.question_text }}</h2>
          <div class="student-options">
            <button 
              v-for="option in question.options" 
              :key="option.option_key" 
              :class="{ selected: selected === option.option_key }" 
              :disabled="submitting" 
              @click="choose(option)"
            >
              <strong>{{ option.option_key }}.</strong>
              <img v-if="option.option_image_url" class="option-image" :src="option.option_image_url" alt="選項圖片" />
              <template v-else>{{ option.option_text }}</template>
            </button>
          </div>
        </template>
        
        <!-- Text input question -->
        <template v-else-if="question.question_type === 'text_input'">
          <img v-if="question.question_image_url" class="question-image" :src="question.question_image_url" alt="題目圖片" />
          <h2 v-if="question.question_text" class="student-question">{{ question.question_text }}</h2>
          <div class="text-input-area">
            <textarea 
              v-model="answerText" 
              placeholder="請輸入你的答案" 
              :disabled="submitting"
              rows="4"
            ></textarea>
            <button class="primary-button" :disabled="submitting || !answerText.trim()" @click="submitTextAnswer">
              {{ submitting ? '提交中…' : '提交答案' }}
            </button>
          </div>
        </template>
        
        <p v-if="errorMessage" class="error-message" role="alert">{{ errorMessage }}</p>
        <p :class="currentResult?.submitted ? 'success-message' : 'pending-message'">
          {{ currentResult?.submitted ? (currentResult?.is_correct === false ? '答錯了' : (currentResult?.is_correct === true ? '答對了' : '答案已提交')) : '請選擇答案' }}
        </p>
        <div class="practice-navigation">
          <button class="secondary-button" :disabled="index === 0" @click="previous">上一題</button>
          <button class="primary-button" :disabled="!currentResult?.submitted" @click="next">
            {{ isLast ? '完成練習' : '下一題' }}
          </button>
        </div>
      </template>
      <template v-else>
        <div class="completion-message">
          <h2>練習已完成</h2>
          <p>你已完成全部 {{ questions.length }} 題。</p>
        </div>
        <button class="secondary-button practice-back-button" @click="restart">返回學生工作台</button>
      </template>
    </section>
  </main>
</template>
