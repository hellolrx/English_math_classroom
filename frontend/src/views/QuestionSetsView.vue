<script setup>
import { onMounted, ref } from 'vue'
import { getQuestionSets, importQuestionSet, previewQuestionSet } from '../api/client'

const fileInput = ref(null)
const selectedFile = ref(null)
const setName = ref('')
const preview = ref(null)
const questionSets = ref([])
const loading = ref(false)
const loadingList = ref(true)
const errorMessage = ref('')
const successMessage = ref('')
const importing = ref(false)
const importedCount = ref(0)

async function loadQuestionSets() {
  loadingList.value = true
  try {
    questionSets.value = await getQuestionSets()
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    loadingList.value = false
  }
}

async function selectFile(event) {
  selectedFile.value = event.target.files?.[0] || null
  preview.value = null
  errorMessage.value = ''
  successMessage.value = ''
  importedCount.value = 0
  if (selectedFile.value) await previewFile()
}

async function previewFile() {
  errorMessage.value = ''
  successMessage.value = ''
  if (!selectedFile.value) {
    errorMessage.value = '請先選擇 .xlsx 文件'
    return
  }
  loading.value = true
  try {
    preview.value = await previewQuestionSet(selectedFile.value)
  } catch (error) {
    errorMessage.value = formatError(error)
  } finally {
    loading.value = false
  }
}

async function submitImport() {
  errorMessage.value = ''
  successMessage.value = ''
  if (!setName.value.trim()) {
    errorMessage.value = '請輸入題目集合名稱'
    return
  }
  if (!selectedFile.value || !preview.value) {
    errorMessage.value = '請先上傳並預覽文件'
    return
  }
  loading.value = true
  importing.value = true
  try {
    const result = await importQuestionSet(setName.value.trim(), selectedFile.value)
    successMessage.value = `已匯入「${result.name}」，共 ${result.question_count} 題`
    importedCount.value = result.question_count
    setName.value = ''
    selectedFile.value = null
    preview.value = null
    if (fileInput.value) fileInput.value.value = ''
    await loadQuestionSets()
  } catch (error) {
    errorMessage.value = formatError(error)
  } finally {
    loading.value = false
    importing.value = false
  }
}

function formatError(error) {
  return error.message || '操作失敗，請稍後再試'
}

function formatDate(value) {
  if (!value) return '未提供日期'
  return new Intl.DateTimeFormat('zh-HK', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

onMounted(loadQuestionSets)
</script>

<template>
  <main class="app-shell">
    <header class="topbar">
      <div>
        <RouterLink class="back-link-inline" to="/teacher">← 返回工作台</RouterLink>
        <p class="eyebrow">QUESTION BANK</p>
        <h1>題目集合</h1>
        <p class="muted">選擇 Excel 後會自動預覽，確認無誤再匯入題庫。</p>
      </div>
    </header>

    <section class="import-panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">IMPORT XLSX</p>
          <h2>匯入新題目集合</h2>
        </div>
      </div>
      <div class="import-grid">
        <label>
          <span>題目集合名稱</span>
          <input v-model="setName" placeholder="例如：S1 Algebra Chapter 1" />
        </label>
        <label>
          <span>Excel 文件</span>
          <input ref="fileInput" type="file" accept=".xlsx" @change="selectFile" />
        </label>
      </div>
      <p class="helper-text">必要欄位：題目、選項A、選項B、選項C、選項D、正確答案。解析欄位可以留空。</p>
      <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
      <p v-if="successMessage" class="success-message">{{ successMessage }}</p>
      <p v-if="importedCount" class="helper-text import-next-step">已匯入 {{ importedCount }} 題並直接發布。</p>
      <RouterLink v-if="importedCount" class="status-pill import-next-step-link" to="/teacher/sessions/new">去工作台建立课堂</RouterLink>
    </section>

    <section v-if="preview" class="preview-panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">PREVIEW</p>
          <h2>{{ preview.filename }}</h2>
          <p class="preview-count">已解析 {{ preview.question_count }} 題，可確認匯入</p>
        </div>
        <span class="status-pill">{{ preview.question_count }} 題</span>
      </div>
      <div class="question-preview-list">
        <article v-for="(question, index) in preview.questions" :key="question.row_number" class="question-preview-card">
          <div class="question-number">{{ index + 1 }}</div>
          <div class="question-preview-body">
            <img v-if="question.question_image_url" class="question-image" :src="question.question_image_url" alt="題目圖片" />
            <h3 v-if="question.question_text">{{ question.question_text }}</h3>
            <div class="option-preview-grid">
              <span v-for="key in ['A', 'B', 'C', 'D']" :key="key" :class="{ correct: key === question.correct_answer }">
                <strong>{{ key }}.</strong>
                <img v-if="question.option_image_urls?.[key]" class="option-image" :src="question.option_image_urls[key]" alt="選項圖片" />
                <template v-else>{{ question.options[key] }}</template>
              </span>
            </div>
            <p v-if="question.explanation" class="helper-text">解析：{{ question.explanation }}</p>
          </div>
        </article>
      </div>
      <div class="preview-confirm-row">
        <p class="helper-text">確認以上題目無誤後，再匯入並發布題目集合。</p>
        <button class="primary-button" type="button" :disabled="loading || importing || !setName.trim()" @click="submitImport">{{ importing ? '正在匯入中…' : '確認匯入並發布' }}</button>
      </div>
    </section>

    <section class="list-panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">YOUR QUESTION SETS</p>
          <h2>已建立的題目集合</h2>
        </div>
      </div>
      <p v-if="loadingList" class="loading-state">正在讀取…</p>
      <p v-else-if="!questionSets.length" class="empty-state">暫時沒有題目集合，先匯入第一份 Excel 吧。</p>
      <div v-else class="set-list">
        <RouterLink v-for="set in questionSets" :key="set.id" :to="`/teacher/question-sets/${set.id}`" class="set-row set-row-link">
          <div>
            <h3>{{ set.name }}</h3>
            <p>{{ set.source_filename || '沒有來源文件' }} · {{ set.status === 'archived' ? '已歸檔' : '已發布' }}</p>
          </div>
          <div class="set-row-meta">
            <span>{{ set.question_count }} 題</span>
            <span class="status-pill">{{ formatDate(set.created_at) }}</span>
          </div>
        </RouterLink>
      </div>
    </section>
  </main>
</template>
