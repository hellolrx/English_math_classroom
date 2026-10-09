<script setup>
import { computed, onMounted, ref } from 'vue'
import { getTeacherTopic, getTeacherTopics, importTopic, previewTopicImport, searchTeacherQuestions } from '../api/client'

const topics = ref([])
const selectedTopicId = ref('')
const fileInput = ref(null)
const file = ref(null)
const preview = ref(null)
const currentTopic = ref(null)
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const success = ref('')
const searchYear = ref('')
const searchResults = ref([])
const searching = ref(false)
const selectedTopic = computed(() => topics.value.find(topic => topic.id === selectedTopicId.value))

async function loadTopics() {
  loading.value = true
  try {
    topics.value = await getTeacherTopics()
    if (!selectedTopicId.value) selectedTopicId.value = topics.value[0]?.id || ''
    if (selectedTopicId.value) currentTopic.value = await getTeacherTopic(selectedTopicId.value)
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
  try { currentTopic.value = await getTeacherTopic(id) } catch (e) { error.value = e.message }
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

async function searchByYear() {
  searching.value = true
  error.value = ''
  try { searchResults.value = await searchTeacherQuestions(searchYear.value) } catch (e) { error.value = e.message } finally { searching.value = false }
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
        <p class="helper-text">Excel 列：来源、题目截图、正确答案。来源填写完整标识，例如 DSE 2022 MT II (2)；答案为 A-D 时自动识别为选择题，留空时识别为非选择题。</p>
        <p v-if="error" class="error-message">{{ error }}</p><p v-if="success" class="success-message">{{ success }}</p><p v-if="busy" class="loading-state">正在处理…</p>
        <section v-if="!preview && currentTopic?.questions?.length" class="current-topic-preview">
          <div class="panel-heading"><div><h3>当前题目预览</h3><p class="muted">点击主题后直接查看当前已发布题目。</p></div></div>
          <article v-for="question in currentTopic.questions" :key="question.id" class="question-preview-card">
            <span class="question-number">{{ question.source_question_number || question.sort_order }}</span><div class="question-preview-body"><img :src="question.question_image_url" class="question-image" alt="题目截图" /><p class="helper-text">{{ question.source_reference }} · 原题第 {{ question.source_question_number }} 题 · {{ question.source_paper }}<template v-if="question.correct_option"> · 答案 {{ question.correct_option }}</template></p></div>
          </article>
        </section>
        <section v-if="preview" class="preview-panel">
          <div class="panel-heading"><div><h3>{{ preview.filename }}</h3><p>预览 {{ preview.question_count }} 题</p></div></div>
          <article v-for="question in preview.questions" :key="question.row_number" class="question-preview-card">
            <span class="question-number">{{ question.source_question_number }}</span><div class="question-preview-body">
              <img v-if="question.question_image_url" class="question-image" :src="question.question_image_url" alt="题目截图" />
              <p v-if="question.question_text">{{ question.question_text }}</p>
              <p class="helper-text">{{ question.question_type === 'single_choice' ? '选择题' : '非选择题' }} · {{ question.source_reference }} · 年份 {{ question.source_year }} · 原题 {{ question.source_question_number }} · {{ question.source_paper }}<template v-if="question.correct_answer"> · 答案 {{ question.correct_answer }}</template></p>
            </div>
          </article>
          <div class="preview-confirm-row"><span class="confirm-label">确认提交</span><button class="primary-button" :disabled="busy" @click="replaceTopic">确认提交</button></div>
        </section>
      </section>
      <section class="detail-panel source-search-panel">
        <div class="panel-heading"><div><p class="eyebrow">SOURCE SEARCH</p><h2>按年份检索题目</h2><p class="muted">输入 2012、2022 等年份，查看对应的完整来源。</p></div></div>
        <form class="source-search-form" @submit.prevent="searchByYear"><input v-model="searchYear" inputmode="numeric" placeholder="例如 2022"><button class="secondary-button" :disabled="searching">{{ searching ? '检索中…' : '检索' }}</button></form>
        <p v-if="searchResults.length === 0 && searchYear" class="empty-state">没有找到对应年份的题目。</p>
        <div v-else class="source-result-list"><div v-for="item in searchResults" :key="item.id" class="source-result-row"><strong>{{ item.source_reference }}</strong><span>{{ item.math_batches?.topics?.code }} · 原题第 {{ item.source_question_number }} 题</span></div></div>
      </section>
    </div>
  </main>
</template>
