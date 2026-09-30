<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import QRCode from 'qrcode'
import { createSession, getClasses, getQuestionSets, getTopics, getPublicSession, startSession } from '../api/client'

const classes = ref([])
const questionSets = ref([])
const topics = ref([])
const selectedGrade = ref('')
const selectedClass = ref('')
const selectedSet = ref('')
const selectedTopic = ref('')
const sourceType = ref('question_set')
const sessionType = ref('classroom')
const timeLimitSeconds = ref(30)
const session = ref(null)
const qrDataUrl = ref('')
const participantCount = ref(0)
const loading = ref(true)
const saving = ref(false)
const entering = ref(false)
const errorMessage = ref('')
let countTimer

const grades = computed(() => [...new Map(classes.value.map(item => [item.grade_id, item.grades || { name: item.grade_id }])).entries()].map(([id, data]) => ({ id, ...data })))
const filteredClasses = computed(() => classes.value.filter(item => item.grade_id === selectedGrade.value))
const selectedClassName = computed(() => filteredClasses.value.find(item => item.id === selectedClass.value)?.name || '')

onMounted(async () => {
  try {
    const [allClasses, allSets, allTopics] = await Promise.all([getClasses(), getQuestionSets(), getTopics()])
    classes.value = allClasses
    questionSets.value = allSets.filter(item => item.status === 'published')
    topics.value = allTopics
    selectedGrade.value = grades.value[0]?.id || ''
    selectedClass.value = filteredClasses.value[0]?.id || ''
    selectedSet.value = questionSets.value[0]?.id || ''
    selectedTopic.value = topics.value[0]?.id || ''
  } catch (e) {
    errorMessage.value = e.message
  } finally {
    loading.value = false
  }
})

onUnmounted(() => clearInterval(countTimer))

function chooseGrade(id) {
  selectedGrade.value = id
  selectedClass.value = filteredClasses.value[0]?.id || ''
}

async function submit() {
  saving.value = true
  errorMessage.value = ''
  try {
    const payload = {
      class_id: selectedClass.value,
      session_type: sessionType.value,
      time_limit_seconds: sessionType.value === 'classroom' ? timeLimitSeconds.value : 0,
    }
    if (sourceType.value === 'topic') {
      payload.topic_id = selectedTopic.value
    } else {
      payload.question_set_id = selectedSet.value
    }
    session.value = await createSession(payload)
    if (sessionType.value === 'classroom') {
      qrDataUrl.value = await QRCode.toDataURL(session.value.join_url, { width: 380, margin: 4, errorCorrectionLevel: 'H', color: { dark: '#000000', light: '#ffffff' } })
      await refreshCount()
      countTimer = setInterval(refrefreshCount, 2000)
    }
  } catch (e) {
    errorMessage.value = e.message
  } finally {
    saving.value = false
  }
}

async function refreshCount() {
  if (!session.value) return
  try {
    participantCount.value = (await getPublicSession(session.value.access_token)).participant_count || 0
  } catch {
    /* session may be expired */
  }
}

async function enterClassroom() {
  entering.value = true
  errorMessage.value = ''
  try {
    await startSession(session.value.id)
    clearInterval(countTimer)
    window.location.href = `/teacher/sessions/${session.value.id}`
  } catch (e) {
    errorMessage.value = e.message
  } finally {
    entering.value = false
  }
}
</script>

<template>
  <main class="app-shell">
    <header class="topbar">
      <div>
        <RouterLink class="back-link-inline" to="/teacher">← 返回老师工作台</RouterLink>
        <p class="eyebrow">SESSION BUILDER</p>
        <h1>{{ sessionType === 'classroom' ? '课堂场次' : '课后练习' }}</h1>
        <p class="muted">先选择年级和班级，再选择题目来源。</p>
      </div>
    </header>

    <p v-if="loading" class="loading-state">正在读取资料…</p>
    <p v-else-if="errorMessage" class="error-message">{{ errorMessage }}</p>

    <section v-else class="detail-panel session-create-panel">
      <div class="selection-block">
        <h2>1. 选择使用方式</h2>
        <div class="choice-grid">
          <button class="choice-card" :class="{ active: sessionType === 'classroom' }" @click="sessionType = 'classroom'">课堂答题</button>
          <button class="choice-card" :class="{ active: sessionType === 'homework' }" @click="sessionType = 'homework'">课后练习</button>
        </div>
      </div>

      <div class="selection-block">
        <h2>2. 选择年级</h2>
        <div class="choice-grid grade-grid">
          <button v-for="grade in grades" :key="grade.id" :class="{ active: selectedGrade === grade.id }" class="choice-card" @click="chooseGrade(grade.id)">{{ grade.name }}</button>
        </div>
      </div>

      <div class="selection-block">
        <h2>3. 选择班级</h2>
        <div class="choice-grid">
          <button v-for="item in filteredClasses" :key="item.id" :class="{ active: selectedClass === item.id }" class="choice-card" @click="selectedClass = item.id">{{ item.name || item.code }}</button>
        </div>
        <p v-if="selectedClass" class="helper-text">已选择：{{ selectedClassName }}</p>
      </div>

      <div class="selection-block">
        <h2>4. 选择题目来源</h2>
        <div class="choice-grid">
          <button class="choice-card" :class="{ active: sourceType === 'question_set' }" @click="sourceType = 'question_set'">题目集合</button>
          <button class="choice-card" :class="{ active: sourceType === 'topic' }" @click="sourceType = 'topic'">主题</button>
        </div>
      </div>

      <div v-if="sourceType === 'question_set'" class="selection-block">
        <h2>5. 选择题目集合</h2>
        <div class="choice-list">
          <button v-for="item in questionSets" :key="item.id" :class="{ active: selectedSet === item.id }" class="choice-row" @click="selectedSet = item.id">
            <span>{{ item.name }}</span>
            <small>{{ item.question_count }} 题</small>
          </button>
        </div>
        <p v-if="!questionSets.length" class="empty-state">目前没有已发布的题目集合，请先到题目管理发布。</p>
      </div>

      <div v-else class="selection-block">
        <h2>5. 选择主题</h2>
        <div class="choice-list">
          <button v-for="item in topics" :key="item.id" :class="{ active: selectedTopic === item.id }" class="choice-row" @click="selectedTopic = item.id">
            <span>{{ item.code }} - {{ item.name }}</span>
          </button>
        </div>
        <p v-if="!topics.length" class="empty-state">目前沒有可用主題。</p>
      </div>

      <div v-if="sessionType === 'classroom'" class="selection-block">
        <h2>6. 每题时间</h2>
        <select v-model.number="timeLimitSeconds" class="text-input">
          <option :value="30">30 秒（默认）</option>
          <option :value="60">60 秒</option>
          <option :value="90">90 秒</option>
          <option :value="120">120 秒</option>
        </select>
      </div>

      <div v-if="!session" class="action-block">
        <button class="primary-button" :disabled="saving || !selectedClass || (!selectedSet && !selectedTopic)" @click="submit">
          {{ saving ? '建立中…' : '建立场次' }}
        </button>
      </div>

      <div v-else class="result-block">
        <p class="success-message">场次建立成功！</p>
        <div v-if="qrDataUrl" class="qr-panel">
          <h3>课堂二维码</h3>
          <img :src="qrDataUrl" alt="课堂二维码" />
          <p class="helper-text">学生扫码进入课堂，当前已有 <strong>{{ participantCount }}</strong> 位学生加入</p>
        </div>
        <p v-else class="helper-text">课后练习码：<strong>{{ session.join_url }}</strong></p>
        <button class="secondary-button" :disabled="entering" @click="enterClassroom">
          {{ entering ? '进入中…' : '进入课堂控制台' }}
        </button>
      </div>
    </section>
  </main>
</template>
