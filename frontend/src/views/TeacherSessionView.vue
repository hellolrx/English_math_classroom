<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getTeacherClassroomStats, nextTeacherClassroom, startTeacherClassroom } from '../api/client'
const route = useRoute(); const state = ref(null); const error = ref(''); const busy = ref(false); let timer
async function load() { try { state.value = await getTeacherClassroomStats(route.params.id); error.value = '' } catch (e) { error.value = e.message } }
async function start() { busy.value = true; try { await startTeacherClassroom(route.params.id); await load() } catch (e) { error.value = e.message } finally { busy.value = false } }
async function next() { busy.value = true; try { await nextTeacherClassroom(route.params.id); await load() } catch (e) { error.value = e.message } finally { busy.value = false } }
onMounted(async () => { await load(); timer = setInterval(load, 2000) }); onUnmounted(() => clearInterval(timer))
</script>
<template><main class="app-shell"><header class="topbar"><div><RouterLink class="back-link-inline" to="/teacher">← 返回老师工作台</RouterLink><p class="eyebrow">LIVE CLASSROOM</p><h1>课堂控制台</h1></div></header><p v-if="error" class="error-message">{{ error }}</p><section v-if="state" class="detail-panel"><div class="session-status"><span class="status-pill">{{ state.status }}</span><span>已加入 {{ state.participant_count }} 人 · 当前提交 {{ state.submitted_count }} 人</span></div><div v-if="state.question" class="live-question"><p class="eyebrow">当前题目 {{ state.question.sort_order }}</p><img :src="state.question.image_url" class="question-image" alt="题目图片"><div class="distribution"><div v-for="key in ['A','B','C','D']" :key="key"><strong>{{ key }}</strong><span>{{ state.question.distribution?.[key] || 0 }}</span></div></div></div><p v-else class="empty-state">课堂等待开始。</p><div class="button-row"><button v-if="state.status === 'waiting'" class="primary-button" :disabled="busy" @click="start">开始课堂</button><button v-else-if="state.status === 'active'" class="primary-button" :disabled="busy" @click="next">下一题</button><RouterLink v-else class="primary-button" to="/teacher/reports">查看统计</RouterLink></div></section></main></template>
