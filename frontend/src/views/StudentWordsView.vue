<script setup>
import { computed, onMounted, ref } from 'vue'
import { getStudentWords, getStudentWordReview, rateStudentWord } from '../api/client'
const grades = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6']
const mode = ref('learn')
const grade = ref('S1')
const words = ref([])
const totalCount = ref(0)
const learnedCount = ref(0)
const roundNumber = ref(1)
const allWords = ref([])
const studentId = ref('')
const repeatRound = ref(false)
const repeatCompletedCount = ref(0)
const index = ref(0)
const revealed = ref(false)
const loading = ref(true)
const saving = ref(false)
const error = ref('')
let loadVersion = 0
const current = computed(() => words.value[index.value])
const canRestart = computed(() => mode.value === 'learn' && totalCount.value > 0 && learnedCount.value === totalCount.value && !current.value)
const progressText = computed(() => {
  if (mode.value === 'review') return `${grade.value} · 本次复习 ${Math.min(index.value, words.value.length)} / ${words.value.length}`
  if (repeatRound.value) return `${grade.value} · 重复学习第 ${roundNumber.value} 轮 · 本轮 ${repeatCompletedCount.value} / ${totalCount.value}`
  return `${grade.value} · 首次学习 ${learnedCount.value} / ${totalCount.value}`
})
const emptyMessage = computed(() => {
  if (!totalCount.value) return `${grade.value} 尚未发布单词词库，请等待老师上传。`
  if (mode.value === 'learn' && repeatRound.value) return `第 ${roundNumber.value} 轮重复学习已完成。你可以再学一轮，也可以切换“复习”查看到期单词。`
  if (mode.value === 'learn') return `已完成 ${grade.value} 的首次学习，共 ${totalCount.value} 个单词。你可以再学一轮，也可以切换“复习”查看到期单词。`
  if (!learnedCount.value) return `${grade.value} 尚未开始学习，请先切换“学习”。`
  return `${grade.value} 暂无到期复习单词。你已学过 ${learnedCount.value} 个单词，到期后会显示在这里。`
})

function repeatStorageKey() {
  return studentId.value ? `hhx_word_repeat:${studentId.value}:${grade.value}` : ''
}

function wordSignature() {
  return allWords.value.map(word => word.id).sort().join(',')
}

function readRepeatState() {
  const key = repeatStorageKey()
  if (!key) return null
  try {
    const state = JSON.parse(localStorage.getItem(key) || 'null')
    return state?.signature === wordSignature() ? state : null
  } catch {
    return null
  }
}

function writeRepeatState(state) {
  const key = repeatStorageKey()
  if (key) localStorage.setItem(key, JSON.stringify({ ...state, signature: wordSignature() }))
}

async function load() {
  const version = ++loadVersion
  const selectedGrade = grade.value
  const selectedMode = mode.value
  loading.value = true
  error.value = ''
  words.value = []
  try {
    const [inventory, review] = await Promise.all([
      getStudentWords(selectedGrade),
      selectedMode === 'review' ? getStudentWordReview(selectedGrade) : Promise.resolve(null),
    ])
    if (version !== loadVersion) return
    totalCount.value = inventory.total_count
    learnedCount.value = inventory.learned_count
    allWords.value = inventory.all_words
    studentId.value = inventory.student_id
    repeatRound.value = false
    repeatCompletedCount.value = 0
    roundNumber.value = 1
    if (selectedMode === 'review') {
      words.value = review
    } else if (inventory.words.length) {
      words.value = inventory.words
    } else {
      const state = readRepeatState()
      if (state) {
        repeatRound.value = true
        roundNumber.value = state.roundNumber
        const completedIds = new Set(state.completedIds)
        repeatCompletedCount.value = completedIds.size
        words.value = state.active ? allWords.value.filter(word => !completedIds.has(word.id)) : []
      } else {
        words.value = []
      }
    }
    index.value = 0
    revealed.value = false
  } catch (e) {
    if (version === loadVersion) error.value = e.message
  } finally {
    if (version === loadVersion) loading.value = false
  }
}

async function rate(rating) {
  const word = current.value
  if (!word || saving.value) return
  saving.value = true
  error.value = ''
  try {
    const id = word.id || word.word_id
    await rateStudentWord({ word_id: id, rating })
    if (mode.value === 'learn') {
      if (repeatRound.value) {
        const state = readRepeatState() || { active: true, roundNumber: roundNumber.value, completedIds: [] }
        const completedIds = [...new Set([...state.completedIds, id])]
        repeatCompletedCount.value = completedIds.length
        writeRepeatState({ ...state, active: completedIds.length < totalCount.value, completedIds })
      } else {
        learnedCount.value = Math.min(totalCount.value, learnedCount.value + 1)
      }
    }
    index.value += 1
    revealed.value = false
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}
async function restartRound() {
  if (saving.value || !allWords.value.length) return
  error.value = ''
  const previous = readRepeatState()
  roundNumber.value = previous ? previous.roundNumber + 1 : 2
  repeatRound.value = true
  repeatCompletedCount.value = 0
  words.value = [...allWords.value]
  index.value = 0
  revealed.value = false
  writeRepeatState({ active: true, roundNumber: roundNumber.value, completedIds: [] })
}
async function switchMode(value) { mode.value = value; await load() }
async function switchGrade(value) { grade.value = value; await load() }
onMounted(load)
</script>
<template>
  <main class="app-shell student-home-shell">
    <header class="topbar"><div>
      <RouterLink class="back-link-inline" to="/student">← 返回学生工作台</RouterLink>
      <p class="eyebrow">VOCABULARY</p><h1>单词学习</h1>
      <p class="muted">学习未学单词；自评后进入复习计划，到期再复习。可自由选择年级。</p>
    </div></header>
    <div class="grade-selector" role="group" aria-label="选择单词年级">
      <button v-for="item in grades" :key="item" class="grade-card" :class="{ active: grade === item }" :disabled="saving" @click="switchGrade(item)">{{ item }}</button>
    </div>
    <div class="choice-grid">
      <button class="choice-card" :class="{ active: mode === 'learn' }" :disabled="saving" @click="switchMode('learn')">学习</button>
      <button class="choice-card" :class="{ active: mode === 'review' }" :disabled="saving" @click="switchMode('review')">复习</button>
    </div>
    <p v-if="loading" class="loading-state">正在读取单词…</p>
    <template v-else>
      <p v-if="error" class="error-message" role="alert">{{ error }}</p>
      <template v-if="!error || current">
        <p class="muted">{{ progressText }}</p>
        <section v-if="current" class="word-card">
          <p class="eyebrow">{{ mode === 'learn' ? '学习' : '复习' }} · {{ index + 1 }} / {{ words.length }}</p>
          <h2>{{ current.word || current.words?.word }}</h2>
          <button v-if="!revealed" class="primary-button" @click="revealed = true">查看词义</button>
          <template v-else>
            <p class="word-meaning">{{ current.meaning || current.words?.meaning }}</p>
            <div class="choice-grid">
              <button class="choice-card" :disabled="saving" @click="rate('forgot')">忘记</button>
              <button class="choice-card" :disabled="saving" @click="rate('fuzzy')">模糊</button>
              <button class="choice-card" :disabled="saving" @click="rate('clear')">清楚记得</button>
            </div>
            <p v-if="saving" class="muted" role="status">正在保存学习进度…</p>
          </template>
        </section>
        <section v-else class="word-card">
          <p class="empty-state" role="status">{{ emptyMessage }}</p>
          <button v-if="canRestart" class="primary-button" :disabled="saving" @click="restartRound">再学一轮</button>
        </section>
      </template>
    </template>
  </main>
</template>
