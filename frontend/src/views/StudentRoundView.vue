<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { finishStudentRound, saveStudentRoundAnswer, startStudentRound } from '../api/client'
import DraftCanvas from '../components/DraftCanvas.vue'

const props = defineProps({ mode: { type: String, required: true } })
const route = useRoute()
const router = useRouter()
const questions = ref([])
const roundId = ref('')
const loading = ref(true)
const busy = ref(false)
const completed = ref(false)
const errorMessage = ref('')
const topicName = ref('')
const saveTimers = new Map()
const saveTasks = new Map()

const confirmedCount = computed(() => questions.value.filter(item => item.state === 'confirmed').length)
const unansweredCount = computed(() => questions.value.filter(item => !item.selected_option && !item.text_answer?.trim() && item.state !== 'confirmed').length)

async function load() {
  try {
    const context = props.mode === 'topic'
      ? { topic_id: String(route.params.id) }
      : { access_code: String(route.params.code) }
    const data = await startStudentRound(context)
    roundId.value = data.round_id
    topicName.value = data.topic_name || ''
    questions.value = data.questions.map(question => ({
      ...question,
      selected_option: question.answer?.selected_option || '',
      text_answer: question.answer?.text_answer || '',
      state: question.answer?.state || '',
      is_correct: question.answer?.is_correct,
    }))
    completed.value = data.status === 'completed'
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    loading.value = false
  }
}

function scheduleDraft(question) {
  if (question.state === 'confirmed' || completed.value) return
  clearTimeout(saveTimers.get(question.id))
  saveTimers.set(question.id, setTimeout(() => saveDraft(question), 350))
}

async function saveDraft(question) {
  if (question.state === 'confirmed' || completed.value) return
  const task = saveStudentRoundAnswer({
    round_id: roundId.value,
    question_id: question.id,
    selected_option: question.selected_option || null,
    text_answer: question.text_answer || null,
    confirm: false,
  })
  saveTasks.set(question.id, task)
  try {
    await task
    if (question.state !== 'confirmed') question.state = 'draft'
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    if (saveTasks.get(question.id) === task) saveTasks.delete(question.id)
  }
}

async function confirmAnswer(question) {
  if (busy.value || completed.value || question.state === 'confirmed') return
  if (question.question_type === 'single_choice' && !question.selected_option) {
    errorMessage.value = '請先選擇 A、B、C 或 D'
    return
  }
  if (question.question_type === 'text_input' && !question.text_answer.trim()) {
    errorMessage.value = '請先輸入答案'
    return
  }
  clearTimeout(saveTimers.get(question.id))
  busy.value = true
  errorMessage.value = ''
  try {
    await saveTasks.get(question.id)
    const result = await saveStudentRoundAnswer({
      round_id: roundId.value,
      question_id: question.id,
      selected_option: question.selected_option || null,
      text_answer: question.text_answer || null,
      confirm: true,
    })
    question.state = 'confirmed'
    question.is_correct = result.is_correct
    question.correct_option = result.correct_option
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    busy.value = false
  }
}

async function submitWholeRound() {
  if (busy.value || completed.value) return
  busy.value = true
  errorMessage.value = ''
  try {
    for (const timer of saveTimers.values()) clearTimeout(timer)
    saveTimers.clear()
    await Promise.all(saveTasks.values())
    const result = await finishStudentRound({
      round_id: roundId.value,
      answers: questions.value.filter(item => item.state !== 'confirmed').map(item => ({
        question_id: item.id,
        selected_option: item.selected_option || null,
        text_answer: item.text_answer || null,
      })),
    })
    const byId = new Map((result.answers || []).map(item => [item.question_id, item]))
    questions.value = questions.value.map(question => {
      const answer = byId.get(question.id)
      return answer ? {
        ...question,
        selected_option: answer.selected_option || '',
        text_answer: answer.text_answer || '',
        state: answer.state,
        is_correct: answer.is_correct,
        correct_option: answer.correct_option,
      } : question
    })
    completed.value = true
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    busy.value = false
  }
}

function restart() {
  router.go(0)
}

onMounted(load)
onBeforeUnmount(() => {
  for (const timer of saveTimers.values()) clearTimeout(timer)
})
</script>

<template>
  <main class="app-shell student-home-shell">
    <header class="topbar">
      <div>
        <button class="back-link-inline" type="button" @click="router.push('/student')">返回學生工作台</button>
        <p class="eyebrow">MATH PRACTICE</p>
        <h1>{{ topicName || (mode === 'topic' ? '主題練習' : '老師指定練習') }}</h1>
        <p class="muted">已確認 {{ confirmedCount }} 題 · 未答 {{ unansweredCount }} 題</p>
      </div>
    </header>
    <p v-if="loading" class="loading-state">正在恢復練習內容…</p>
    <p v-else-if="errorMessage && !questions.length" class="error-message" role="alert">{{ errorMessage }}</p>
    <template v-else>
      <p v-if="errorMessage" class="error-message" role="alert">{{ errorMessage }}</p>
      <p v-if="completed" class="success-message">本輪已提交。重新練習會建立新的答題輪次。</p>
      <section class="student-round-list">
        <article v-for="(question, index) in questions" :key="question.id" class="student-round-question">
          <h2>第 {{ index + 1 }} 題</h2>
          <img :src="question.image_url" :alt="`第 ${index + 1} 題`" class="question-image" />
          <div v-if="question.question_type === 'single_choice'" class="student-options fixed-options">
            <button v-for="letter in ['A', 'B', 'C', 'D']" :key="letter"
              :class="{ selected: question.selected_option === letter }"
              :disabled="busy || completed || question.state === 'confirmed'"
              @click="question.selected_option = letter; scheduleDraft(question)">
              {{ letter }}
            </button>
          </div>
          <label v-else class="round-text-answer">
            <span>你的答案</span>
            <textarea v-model="question.text_answer" :disabled="busy || completed || question.state === 'confirmed'"
              rows="3" placeholder="輸入答案" @input="scheduleDraft(question)" />
          </label>
          <div class="round-answer-actions">
            <button class="secondary-button" :disabled="busy || completed || question.state === 'confirmed'"
              @click="confirmAnswer(question)">確定本題</button>
            <span v-if="question.state === 'confirmed' && question.question_type === 'single_choice'"
              :class="question.is_correct ? 'success-message' : 'error-message'">
              {{ question.is_correct ? '答對' : `答錯，正確答案 ${question.correct_option}` }}
            </span>
            <span v-else-if="question.state === 'confirmed'" class="pending-message">已提交，老師查看答案</span>
            <span v-else-if="question.state === 'draft'" class="muted">草稿已保存</span>
          </div>
        </article>
      </section>
      <div class="round-submit-bar">
        <p v-if="!completed" class="muted">可以逐題確定，也可以最後整份提交；未答題會標記為未答。</p>
        <button v-if="!completed" class="primary-button" :disabled="busy || !questions.length" @click="submitWholeRound">
          {{ busy ? '提交中…' : `整份提交（未答 ${unansweredCount} 題）` }}
        </button>
        <button v-else class="primary-button" @click="restart">重新練習</button>
      </div>
      <DraftCanvas :question-key="roundId" />
    </template>
  </main>
</template>
