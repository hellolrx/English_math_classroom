<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getClasses, getVocabularyByGrade, previewVocabulary, importVocabulary } from '../api/client'

const router = useRouter()
const grades = ref([])
const selectedGrade = ref('')
const words = ref([])
const preview = ref(null)
const loading = ref(true)
const importing = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const file = ref(null)

async function load() {
  try {
    grades.value = await getClasses()
    if (grades.value.length) {
      selectedGrade.value = grades.value[0].id
      await loadWords()
    }
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    loading.value = false
  }
}

async function loadWords() {
  try {
    words.value = await getVocabularyByGrade(selectedGrade.value)
  } catch (error) {
    errorMessage.value = error.message
  }
}

async function onFileChange(event) {
  file.value = event.target.files[0]
  errorMessage.value = ''
  successMessage.value = ''
  
  if (file.value) {
    try {
      preview.value = await previewVocabulary(file.value)
      if (preview.value.status === 'error') {
        errorMessage.value = preview.value.errors?.join('; ') || '文件解析失敗'
      }
    } catch (error) {
      errorMessage.value = error.message
    }
  }
}

async function doImport() {
  if (!file.value || !selectedGrade.value) return
  importing.value = true
  errorMessage.value = ''
  successMessage.value = ''
  
  try {
    const result = await importVocabulary(file.value, selectedGrade.value)
    successMessage.value = `成功導入 ${result.imported_count} 個單詞`
    file.value = null
    preview.value = null
    await loadWords()
  } catch (error) {
    errorMessage.value = error.detail?.errors?.join('; ') || error.message
  } finally {
    importing.value = false
  }
}

onMounted(load)
</script>

<template>
  <main class="app-shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">ENGLISH MATH CLASSROOM</p>
        <h1>單詞管理</h1>
      </div>
      <RouterLink class="text-button" to="/teacher">返回工作台</RouterLink>
    </header>

    <p v-if="loading" class="loading-state">正在讀取資料…</p>
    <p v-else-if="errorMessage" class="error-message">{{ errorMessage }}</p>
    <p v-else-if="successMessage" class="success-message">{{ successMessage }}</p>
    <template v-else>
      <section class="vocabulary-import-section">
        <div class="import-header">
          <div>
            <h2>上傳單詞表</h2>
            <p class="muted">上傳 Excel 文件（English_word.xlsx 格式，包含單詞和詞義兩列）</p>
          </div>
          <select v-model="selectedGrade" @change="loadWords">
            <option v-for="grade in grades" :key="grade.id" :value="grade.id">
              {{ grade.name }}
            </option>
          </select>
        </div>

        <div class="import-form">
          <input type="file" accept=".xlsx,.xls" @change="onFileChange" />
          <button class="primary-button" :disabled="!file || importing" @click="doImport">
            {{ importing ? '導入中…' : '導入單詞' }}
          </button>
        </div>

        <div v-if="preview && preview.status === 'preview'" class="preview-panel">
          <h3>預覽（共 {{ preview.count }} 個單詞）</h3>
          <div class="preview-table">
            <div class="preview-row preview-header">
              <span>行號</span>
              <span>單詞</span>
              <span>詞義</span>
            </div>
            <div v-for="word in preview.words.slice(0, 20)" :key="word.row_number" class="preview-row">
              <span>{{ word.row_number }}</span>
              <span>{{ word.word }}</span>
              <span>{{ word.meaning }}</span>
            </div>
            <div v-if="preview.count > 20" class="preview-more">
              ... 還有 {{ preview.count - 20 }} 個單詞
            </div>
          </div>
        </div>
      </section>

      <section class="vocabulary-list-section">
        <h2>單詞列表（共 {{ words.length }} 個）</h2>
        <div class="word-table">
          <div class="word-row word-header">
            <span>單詞</span>
            <span>詞義</span>
            <span>排序</span>
          </div>
          <div v-for="word in words" :key="word.id" class="word-row">
            <span class="word-text">{{ word.word }}</span>
            <span class="word-meaning">{{ word.meaning }}</span>
            <span class="word-sort">{{ word.sort_order }}</span>
          </div>
        </div>
      </section>
    </template>
  </main>
</template>

<style scoped>
.vocabulary-import-section {
  background: white;
  border-radius: 16px;
  padding: 24px;
  margin-bottom: 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.import-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.import-header h2 {
  margin: 0 0 8px 0;
  font-size: 18px;
}

.import-header select {
  padding: 10px 16px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 14px;
}

.import-form {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 20px;
}

.import-form input[type="file"] {
  flex: 1;
}

.preview-panel {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #e5e7eb;
}

.preview-panel h3 {
  margin: 0 0 12px 0;
  font-size: 16px;
}

.preview-table {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

.preview-row {
  display: grid;
  grid-template-columns: 60px 1fr 2fr;
  padding: 12px 16px;
  border-bottom: 1px solid #e5e7eb;
}

.preview-row:last-child {
  border-bottom: none;
}

.preview-header {
  background: #f9fafb;
  font-weight: 600;
  font-size: 12px;
  text-transform: uppercase;
}

.preview-more {
  padding: 12px 16px;
  text-align: center;
  color: #6b7280;
  font-size: 14px;
}

.vocabulary-list-section {
  background: white;
  border-radius: 16px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.vocabulary-list-section h2 {
  margin: 0 0 16px 0;
  font-size: 18px;
}

.word-table {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

.word-row {
  display: grid;
  grid-template-columns: 1fr 2fr 80px;
  padding: 12px 16px;
  border-bottom: 1px solid #e5e7eb;
}

.word-row:last-child {
  border-bottom: none;
}

.word-header {
  background: #f9fafb;
  font-weight: 600;
  font-size: 12px;
  text-transform: uppercase;
}

.word-text {
  font-weight: 500;
}

.word-meaning {
  color: #6b7280;
}

.word-sort {
  color: #9ca3af;
  font-size: 14px;
}

.success-message {
  background: #d1fae5;
  color: #065f46;
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 16px;
}
</style>
