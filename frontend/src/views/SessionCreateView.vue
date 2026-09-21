<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import QRCode from 'qrcode'
import { createSession, getClasses, getQuestionSet } from '../api/client'

const route = useRoute(); const router = useRouter()
const classes = ref([]); const questionSet = ref(null); const classId = ref(''); const session = ref(null)
const qrDataUrl = ref(''); const loading = ref(true); const saving = ref(false); const errorMessage = ref('')
onMounted(async () => { try { [classes.value, questionSet.value] = await Promise.all([getClasses(), getQuestionSet(route.query.questionSetId)]); classId.value = classes.value[0]?.id || '' } catch (e) { errorMessage.value = e.message } finally { loading.value = false } })
async function submit() { saving.value = true; errorMessage.value = ''; try { session.value = await createSession({ question_set_id: route.query.questionSetId, class_id: classId.value }); qrDataUrl.value = await QRCode.toDataURL(session.value.join_url, { width: 300, margin: 2 }) } catch (e) { errorMessage.value = e.message } finally { saving.value = false } }
</script>
<template><main class="app-shell"><header class="topbar"><div><RouterLink class="back-link-inline" to="/teacher/question-sets">← 返回題目集合</RouterLink><p class="eyebrow">CLASSROOM SESSION</p><h1>建立课堂场次</h1><p class="muted">{{ questionSet?.name }} · 二维码默认有效 7 天</p></div></header><p v-if="loading" class="loading-state">正在读取资料…</p><p v-else-if="errorMessage" class="error-message">{{ errorMessage }}</p><section v-else class="detail-panel"><label>选择班级<select v-model="classId"><option v-for="item in classes" :key="item.id" :value="item.id">{{ item.grades?.name }} {{ item.name || item.code }}</option></select></label><button class="primary-button" :disabled="saving || !classId" @click="submit">{{ saving ? '建立中…' : '建立课堂并生成二维码' }}</button><div v-if="session" class="session-created"><img :src="qrDataUrl" alt="课堂二维码" class="qr-code"><p class="success-message">课堂已建立，共 {{ session.question_count }} 题</p><p class="helper-text">请让学生扫描此二维码：<br><a :href="session.join_url" target="_blank">{{ session.join_url }}</a></p><RouterLink class="primary-button inline-button" :to="`/teacher/sessions/${session.id}`">进入课堂控制台</RouterLink></div></section></main></template>
