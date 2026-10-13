<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { answerClassroom, getClassroom, joinClassroom } from '../api/client'
import DraftCanvas from '../components/DraftCanvas.vue'
const route = useRoute(); const token = String(route.params.token); const state = ref(null); const selected = ref(''); const error = ref(''); const now = ref(Date.now()); let timer; let clock; let loading = false; let disposed = false
const remaining = computed(() => { const deadline = state.value?.deadline_at; return deadline ? Math.max(0, Math.ceil((Date.parse(deadline) - now.value) / 1000)) : null })
watch(() => state.value?.question?.id, () => { selected.value = '' })
async function load() {
  if (loading || disposed) return
  loading = true
  try {
    const next = await getClassroom(token)
    if (!disposed) {
      state.value = next
      error.value = ''
      if (next.status === 'closed' || next.status === 'invalidated') clearInterval(timer)
    }
  } catch (e) {
    if (!disposed) error.value = e.message
  } finally { loading = false }
}
async function submit(letter) { if (!state.value?.question || state.value.question_status !== 'open') return; try { await answerClassroom(token, { question_id: state.value.question.id, selected_option: letter }); selected.value = letter } catch (e) { error.value = e.message } }
onMounted(async () => { try { await joinClassroom(token) } catch (e) { error.value = e.message } await load(); if (disposed) return; if (state.value?.status !== 'closed') timer = setInterval(load, 2000); clock = setInterval(() => { now.value = Date.now() }, 250) }); onUnmounted(() => { disposed = true; clearInterval(timer); clearInterval(clock) })
</script>
<template>
  <main class="auth-shell student-ui">
    <section class="auth-card student-card student-session-card">
      <div class="brand-mark student-mark">答</div>
      <p class="eyebrow">ENGLISH MATH CLASSROOM</p>
      <h1>课堂答题</h1>
      <p v-if="error" class="error-message" role="alert">{{ error }}</p>
      <p v-else-if="!state" class="loading-state">正在连接课堂…</p>
      <template v-else-if="state.status === 'waiting'">
        <p class="participant-count">已进入课堂：{{ state.participant_count || 0 }} 人</p>
        <p class="muted">等待老师开始。</p>
      </template>
      <template v-else-if="state.status === 'active' && state.question_status === 'open' && state.question">
        <p v-if="remaining !== null" class="countdown" :class="{ urgent: remaining <= 5 }">剩余 {{ remaining }} 秒</p>
        <img :src="state.question.image_url" class="question-image" alt="题目图片">
        <div class="student-options fixed-options">
          <button v-for="letter in ['A','B','C','D']" :key="letter" :class="{ selected: selected === letter }" :disabled="remaining === 0" @click="submit(letter)">{{ letter }}</button>
        </div>
        <p class="muted">课堂中暂不显示对错，由老师统一讲解。</p>
      </template>
      <template v-else-if="state.status === 'closed'">
        <div class="completion-message"><h2>课堂已完成</h2><p>本次课堂已经结束，答题记录已保存。</p></div>
        <RouterLink class="back-link" to="/student">返回学生工作台</RouterLink>
      </template>
      <template v-else><p class="muted">正在同步课堂状态，请稍候…</p></template>
      <DraftCanvas v-if="state?.status === 'active'" :question-key="state?.question?.id" />
    </section>
  </main>
</template>
