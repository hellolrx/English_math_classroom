<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({ questionKey: { type: [String, Number], default: '' } })
const canvas = ref(null)
const open = ref(false)
let drawing = false

function resize() {
  if (!canvas.value) return
  const ratio = window.devicePixelRatio || 1
  const context = canvas.value.getContext('2d')
  const old = canvas.value.toDataURL()
  canvas.value.width = window.innerWidth * ratio
  canvas.value.height = window.innerHeight * ratio
  canvas.value.style.width = `${window.innerWidth}px`
  canvas.value.style.height = `${window.innerHeight}px`
  context.setTransform(ratio, 0, 0, ratio, 0, 0)
  context.lineCap = 'round'
  context.lineJoin = 'round'
  context.lineWidth = 3
  context.strokeStyle = '#111827'
  if (old !== 'data:,') { const image = new Image(); image.onload = () => context.drawImage(image, 0, 0, window.innerWidth, window.innerHeight); image.src = old }
}
function clearCanvas() { if (!canvas.value) return; canvas.value.getContext('2d').clearRect(0, 0, window.innerWidth, window.innerHeight) }
function point(event) { const rect = canvas.value.getBoundingClientRect(); return { x: event.clientX - rect.left, y: event.clientY - rect.top } }
function start(event) { drawing = true; canvas.value.setPointerCapture(event.pointerId); const p = point(event); const context = canvas.value.getContext('2d'); context.beginPath(); context.moveTo(p.x, p.y) }
function draw(event) { if (!drawing) return; const p = point(event); const context = canvas.value.getContext('2d'); context.lineTo(p.x, p.y); context.stroke() }
function stop() { drawing = false }
async function show() { open.value = true; await nextTick(); resize() }
function hide() { open.value = false; drawing = false }
watch(() => props.questionKey, () => { if (open.value) clearCanvas() })
window.addEventListener('resize', resize)
onBeforeUnmount(() => window.removeEventListener('resize', resize))
</script>

<template>
  <button class="draft-toggle" type="button" @click="show">草稿紙</button>
  <div v-if="open" class="draft-overlay">
    <canvas ref="canvas" class="draft-canvas" @pointerdown="start" @pointermove="draw" @pointerup="stop" @pointercancel="stop" @pointerleave="stop" />
    <div class="draft-toolbar"><button type="button" class="secondary-button" @click="clearCanvas">清空</button><button type="button" class="primary-button" @click="hide">關閉</button></div>
  </div>
</template>
