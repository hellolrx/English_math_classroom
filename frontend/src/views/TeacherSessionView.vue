<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getTeacherClassroomStats, nextTeacherClassroom, startTeacherClassroom } from '../api/client'
const route = useRoute(); const state = ref(null); const error = ref(''); const busy = ref(false); let timer
const reportLink = computed(() => ({ path: '/teacher/reports', query: { session_id: String(route.params.id) } }))
const statusLabel = computed(() => ({ waiting: '等待開始', active: '課堂進行中', closed: '課堂已結束' }[state.value?.status] || '正在連接'))
const answerCount = computed(() => ['A', 'B', 'C', 'D'].reduce((sum, key) => sum + (state.value?.question?.distribution?.[key] || 0), 0))
const projection = ref(false)
async function load() { try { state.value = await getTeacherClassroomStats(route.params.id); error.value = '' } catch (e) { error.value = e.message } }
async function start() { busy.value = true; try { await startTeacherClassroom(route.params.id); await load() } catch (e) { error.value = e.message } finally { busy.value = false } }
async function next() { busy.value = true; try { await nextTeacherClassroom(route.params.id); await load() } catch (e) { error.value = e.message } finally { busy.value = false } }
onMounted(async () => { await load(); timer = setInterval(load, 2000) }); onUnmounted(() => clearInterval(timer))
</script>
<template>
  <main class="app-shell teacher-ui teacher-classroom" :class="{ 'teacher-projection': projection }">
    <header class="topbar">
      <div>
        <RouterLink v-if="!projection" class="back-link-inline" to="/teacher">← 返回老师工作台</RouterLink>
        <p class="eyebrow">LIVE CLASSROOM</p><h1>课堂控制台</h1>
      </div>
      <button class="secondary-button" :aria-pressed="projection" @click="projection = !projection">{{ projection ? '退出投影布局' : '投影布局' }}</button>
    </header>
    <p v-if="error" class="error-message" role="alert">{{ error }}</p>
    <p v-if="!state && !error" class="loading-state" role="status">正在连接课堂…</p>
    <section v-if="state" class="detail-panel">
      <div class="session-status">
        <span class="status-pill" :class="`classroom-status-${state.status}`">{{ statusLabel }}</span>
        <div class="classroom-counters"><span>已加入 <strong>{{ state.participant_count }}</strong> 人</span><span>当前提交 <strong>{{ state.submitted_count }}</strong> 人</span></div>
      </div>
      <div v-if="state.question && state.status !== 'closed'" class="live-question">
        <p class="eyebrow">当前题目 {{ state.question.sort_order }}</p>
        <Transition name="classroom-question" mode="out-in">
          <img :key="state.question.id || state.question.sort_order" :src="state.question.image_url" class="question-image" alt="题目图片">
        </Transition>
        <div class="distribution" aria-label="各选项提交人数">
          <div v-for="(key, index) in ['A','B','C','D']" :key="key" :class="`answer-tone-${index}`">
            <strong>{{ key }}</strong><span>{{ state.question.distribution?.[key] || 0 }} <small>人</small></span>
            <div class="answer-meter" aria-hidden="true"><i :style="{ width: `${answerCount ? (state.question.distribution?.[key] || 0) / answerCount * 100 : 0}%` }"></i></div>
          </div>
        </div>
      </div>
      <div v-else-if="state.status === 'waiting'" class="classroom-waiting">
        <span class="classroom-board-mark" aria-hidden="true">x + y</span><h2>一起準備，開始這堂課</h2><p class="muted">學生加入後，點擊「开始课堂」顯示第一題。</p>
      </div>
      <div v-if="state.status === 'closed'" class="completion-message"><h2>题目已经做完</h2><p>课堂答题记录已经保存，可以查看本场课堂所有参与学生的统计。</p></div>
      <div class="button-row classroom-action-row">
        <button v-if="state.status === 'waiting'" class="primary-button" :disabled="busy" @click="start">{{ busy ? '正在开始…' : '开始课堂' }}</button>
        <button v-else-if="state.status === 'active'" class="primary-button" :disabled="busy" @click="next">{{ busy ? '正在切换…' : '下一题' }}</button>
        <RouterLink v-else class="primary-button" :to="reportLink">查看统计</RouterLink>
      </div>
    </section>
  </main>
</template>
