<script setup>
import { computed, onMounted, ref } from 'vue'
import { getTeacherTopics, importTopic, previewTopicImport } from '../api/client'

const topics = ref([])
const selectedTopicId = ref('')
const fileInput = ref(null)
const file = ref(null)
const preview = ref(null)
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const success = ref('')
const selectedTopic = computed(() => topics.value.find(topic => topic.id === selectedTopicId.value))

async function loadTopics() {
  loading.value = true
  try {
    topics.value = await getTeacherTopics()
    if (!selectedTopicId.value) selectedTopicId.value = topics.value[0]?.id || ''
  } catch (e) { error.value = e.message } finally { loading.value = false }
}

async function chooseFile(event) {
  file.value = event.target.files?.[0] || null
  preview.value = null
  success.value = ''
  error.value = ''
  if (!file.value || !selectedTopicId.value) return
  busy.value = true
  try { preview.value = await previewTopicImport(selectedTopicId.value, file.value) } catch (e) { error.value = typeof e.message === 'string' ? e.message : JSON.stringify(e.message) } finally { busy.value = false }
}

async function selectTopic(id) {
  selectedTopicId.value = id
  file.value = null
  preview.value = null
  if (fileInput.value) fileInput.value.value = ''
  error.value = ''
  success.value = ''
}

async function replaceTopic() {
  if (!file.value || !preview.value || !selectedTopic.value) return
  const accepted = window.confirm(`将用 ${preview.value.question_count} 道题替换「${selectedTopic.value.code} ${selectedTopic.value.name}」当前题库。旧练习码与进行中的课堂会失效，历史答题保留。继续吗？`)
  if (!accepted) return
  busy.value = true
  error.value = ''
  success.value = ''
  try {
    const result = await importTopic(selectedTopicId.value, file.value)
    success.value = `已替换 ${selectedTopic.value.code}，发布 ${result.question_count} 道题。`
    file.value = null
    preview.value = null
    if (fileInput.value) fileInput.value.value = ''
    await loadTopics()
  } catch (e) { error.value = typeof e.message === 'string' ? e.message : JSON.stringify(e.message) } finally { busy.value = false }
}

onMounted(loadTopics)
</script>

<template>
  <main class="app-shell">
    <header class="topbar"><div><RouterLink class="back-link-inline" to="/teacher">← 返回老师工作台</RouterLink><p class="eyebrow">MATH TOPICS</p><h1>数学题库</h1><p class="muted">每个主题单独覆盖；学生旧答题记录保留在原批次。</p></div></header>
    <p v-if="loading" class="loading-state">正在读取主题…</p>
    <p v-else-if="error && !selectedTopic" class="error-message">{{ error }}</p>
    <div v-else class="topic-admin-layout">
      <aside class="topic-admin-list" aria-label="主题列表">
        <button v-for="topic in topics" :key="topic.id" class="choice-row" :class="{ active: selectedTopicId === topic.id }" @click="selectTopic(topic.id)">
          <span><strong>{{ topic.code }}</strong> {{ topic.name }}<small>{{ topic.question_count }} 题 · {{ topic.batch_status === 'published' ? '已发布' : '未导入' }}</small></span>
        </button>
      </aside>
      <section v-if="selectedTopic" class="topic-admin-content">
        <div class="panel-heading"><div><p class="eyebrow">{{ selectedTopic.code }}</p><h2>{{ selectedTopic.name }}</h2><p class="muted">当前题量：{{ selectedTopic.question_count }}</p><RouterLink class="back-link-inline" :to="`/teacher/question-sets/${selectedTopic.id}`">查看当前题目</RouterLink></div></div>
        <label class="topic-upload"><span>选择 Excel 文件</span><input ref="fileInput" type="file" accept=".xlsx" @change="chooseFile"></label>
        <p class="helper-text">Excel 列：题目截图、正确答案、题型、年份。题型填写“选择题”或“非选择题”；选择题答案为 A-D，非选择题答案留空。</p>
        <p v-if="error" class="error-message">{{ error }}</p><p v-if="success" class="success-message">{{ success }}</p><p v-if="busy" class="loading-state">正在处理…</p>
        <section v-if="preview" class="preview-panel">
          <div class="panel-heading"><div><h3>{{ preview.filename }}</h3><p>预览 {{ preview.question_count }} 题</p></div></div>
          <article v-for="(question, index) in preview.questions" :key="question.row_number" class="question-preview-card">
            <span class="question-number">{{ index + 1 }}</span><div class="question-preview-body">
              <img v-if="question.question_image_url" class="question-image" :src="question.question_image_url" alt="题目截图" />
              <p v-if="question.question_text">{{ question.question_text }}</p>
              <p class="helper-text">{{ question.question_type === 'single_choice' ? '选择题' : '非选择题' }} · {{ question.source_year || '未填写年份' }}<template v-if="question.correct_answer"> · 答案 {{ question.correct_answer }}</template></p>
            </div>
          </article>
          <button class="primary-button" :disabled="busy" @click="replaceTopic">确认覆盖此主题</button>
        </section>
      </section>
    </div>
  </main>
</template>
