<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getTeacherTopic } from '../api/client'

const route = useRoute()
const topic = ref(null)
const loading = ref(true)
const error = ref('')
onMounted(async () => {
  try { topic.value = await getTeacherTopic(route.params.id) } catch (e) { error.value = e.message } finally { loading.value = false }
})
</script>

<template>
  <main class="app-shell">
    <header class="topbar"><div><RouterLink class="back-link-inline" to="/teacher/question-sets">← 返回数学题库</RouterLink><p class="eyebrow">TOPIC CONTENT</p><h1>{{ topic ? `${topic.code} · ${topic.name}` : '主题题目' }}</h1></div></header>
    <p v-if="loading" class="loading-state">正在读取题目…</p><p v-else-if="error" class="error-message">{{ error }}</p>
    <section v-else class="detail-panel">
      <p v-if="!topic.questions.length" class="empty-state">此主题尚未导入题目。</p>
      <article v-for="question in topic.questions" :key="question.id" class="question-preview-card">
        <span class="question-number">{{ question.sort_order }}</span><div class="question-preview-body">
          <img :src="question.question_image_url" class="question-image" alt="题目截图" />
          <p class="helper-text">{{ question.question_type === 'single_choice' ? '选择题' : '非选择题' }} · {{ question.source_reference || '未填写来源' }} · 年份 {{ question.source_year || '未解析' }} · 原题 {{ question.source_question_number || '未解析' }} · {{ question.source_paper || '未解析' }}<template v-if="question.correct_option"> · 答案 {{ question.correct_option }}</template></p>
        </div>
      </article>
    </section>
  </main>
</template>
