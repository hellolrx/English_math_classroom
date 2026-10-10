<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getClasses, getTeacherPracticeSummary, getTeacherTopics } from '../api/client'

const route = useRoute()
const classes = ref([])
const topics = ref([])
const selectedClassId = ref('')
const selectedBatchId = ref('')
const report = ref(null)
const loading = ref(true)
const loadingReport = ref(false)
const error = ref('')

async function loadReport() {
  if (!selectedClassId.value || !selectedBatchId.value) {
    report.value = null
    return
  }
  loadingReport.value = true
  error.value = ''
  try {
    report.value = await getTeacherPracticeSummary(selectedClassId.value, selectedBatchId.value)
  } catch (e) {
    report.value = null
    error.value = e.message
  } finally {
    loadingReport.value = false
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [classRows, topicRows] = await Promise.all([getClasses(), getTeacherTopics()])
    classes.value = classRows
    topics.value = topicRows.filter(item => item.batch_id)
    const requestedClassId = typeof route.query.class_id === 'string' ? route.query.class_id : ''
    const requestedBatchId = typeof route.query.batch_id === 'string' ? route.query.batch_id : ''
    selectedClassId.value = classes.value.some(item => item.id === requestedClassId) ? requestedClassId : (classes.value[0]?.id || '')
    selectedBatchId.value = topics.value.some(item => item.batch_id === requestedBatchId) ? requestedBatchId : (topics.value[0]?.batch_id || '')
    await loadReport()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function percent(count, total) {
  return total ? `${Math.round(count / total * 100)}%` : '0%'
}

onMounted(load)
</script>

<template>
  <main class="app-shell">
    <header class="topbar">
      <div><RouterLink class="back-link-inline" to="/teacher">← 返回老师工作台</RouterLink><p class="eyebrow">REPORTS</p><h1>习题统计</h1><p class="muted">选择班级和当前题库，合并查看课堂、自主练习与练习码作答。</p></div>
    </header>
    <p v-if="loading" class="loading-state">正在读取统计资料…</p>
    <p v-else-if="error && !report" class="error-message">{{ error }}</p>
    <section v-else class="detail-panel report-workspace">
      <div class="report-filters">
        <label><span>班级</span><select v-model="selectedClassId" class="text-input" @change="loadReport"><option v-for="item in classes" :key="item.id" :value="item.id">{{ item.grades?.name }} · {{ item.name }}</option></select></label>
        <label><span>当前题库</span><select v-model="selectedBatchId" class="text-input" @change="loadReport"><option v-for="item in topics" :key="item.batch_id" :value="item.batch_id">{{ item.code }} · {{ item.name }}</option></select></label>
      </div>
      <p v-if="loadingReport" class="loading-state">正在计算班级统计…</p>
      <template v-else-if="report">
        <div class="report-context"><strong>{{ report.title }}</strong><span>{{ report.class?.name }} · 班级人数 {{ report.student_count }} · 有作答 {{ report.participant_count }} 人</span></div>
        <article v-for="question in report.questions" :key="question.id" class="report-question">
          <div class="report-question-heading"><div><span class="question-number">{{ question.sort_order }}</span><strong>{{ question.question_type === 'single_choice' ? '选择题' : '非选择题' }}</strong></div><span v-if="question.question_type === 'single_choice'">正确率 {{ question.accuracy }}%</span></div>
          <p class="correct-answer">{{ question.question_type === 'single_choice' ? `正确答案：${question.correct_option}` : '不自动判分' }} · 已作答 {{ question.submitted_count }} 人 · 未作答 {{ question.unanswered_count }} 人</p>
          <div v-if="question.question_type === 'single_choice'" class="report-bars"><div v-for="key in ['A','B','C','D']" :key="key" class="report-bar"><span>{{ key }}</span><div><i :style="{ width: percent(question.distribution[key], question.submitted_count) }"></i></div><b><strong>{{ question.distribution[key] }}</strong><small>{{ percent(question.distribution[key], question.submitted_count) }}</small></b></div></div>
          <div v-if="question.question_type !== 'single_choice'" class="text-answer-list"><p class="helper-text">文字答案</p><p v-if="!question.text_answers?.length" class="empty-state">目前没有文字答案。</p><div v-for="answer in question.text_answers" :key="`${question.id}-${answer.student_id}`" class="text-answer-row"><strong>{{ answer.name || '未命名学生' }}</strong><span>{{ answer.student_number || '无学号' }} · {{ answer.class?.name || answer.class?.code || '无班级' }}</span><p>{{ answer.answer }}</p></div></div>
          <p class="helper-text">答对 {{ question.correct_count }} 人</p>
        </article>
      </template>
      <p v-else class="empty-state">请选择班级和题库查看统计。</p>
    </section>
  </main>
</template>
