<script setup>
import { computed, onMounted, ref } from 'vue'
import { getReviewWords, rateWord } from '../api/client'

const words = ref([])
const index = ref(0)
const submitted = ref(false)
const loading = ref(true)
const errorMessage = ref('')
const busy = ref(false)
const currentRating = ref('')

const word = computed(() => words.value[index.value])
const isLast = computed(() => index.value >= words.value.length - 1)

async function load() {
  try {
    words.value = await getReviewWords()
    index.value = 0
    submitted.value = false
    currentRating.value = ''
  } catch (e) {
    errorMessage.value = e.message
  } finally {
    loading.value = false
  }
}

async function rate(rating) {
  if (!word.value || busy.value || currentRating.value) return
  busy.value = true
  currentRating.value = rating
  try {
    await rateWord({
      word_id: word.value.word_id,
      rating: rating,
    })
    submitted.value = true
    
    // Delay before moving to next word
    setTimeout(() => {
      if (!isLast.value) {
        index.value += 1
        submitted.value = false
        currentRating.value = ''
      } else {
        // Load new review words
        load()
      }
    }, 1000)
  } catch (e) {
    errorMessage.value = e.message
    currentRating.value = ''
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <main class="auth-shell">
    <section class="auth-card student-card student-session-card">
      <RouterLink class="back-link-inline" to="/student">← 返回學生工作台</RouterLink>
      <p class="eyebrow">VOCABULARY REVIEW</p>
      <h1>背單詞</h1>
      
      <div v-if="loading" class="loading-state">正在載入單詞…</div>
      <p v-else-if="errorMessage" class="error-message">{{ errorMessage }}</p>
      
      <template v-else-if="word">
        <div class="review-progress">第 {{ index + 1 }} / {{ words.length }} 個</div>
        <div class="word-display">
          <h2 class="word-text">{{ word.word }}</h2>
          <p v-if="word.meaning" class="word-meaning">{{ word.meaning }}</p>
          <p v-if="word.familiarity_level" class="word-level">熟練度：{{ word.familiarity_level }}/10</p>
        </div>
        
        <template v-if="!submitted">
          <p class="muted">你記得這個單詞嗎？</p>
          <div class="review-rating-row">
            <button 
              class="review-button review-forgot" 
              :disabled="busy" 
              @click="rate('forgot')"
            >
              忘記
            </button>
            <button 
              class="review-button review-fuzzy" 
              :disabled="busy" 
              @click="rate('fuzzy')"
            >
              模糊
            </button>
            <button 
              class="review-button review-clear" 
              :disabled="busy" 
              @click="rate('clear')"
            >
              清楚記得
            </button>
          </div>
        </template>
        
        <template v-else>
          <p class="success-message">已記錄，正在切換下一個單詞…</p>
        </template>
      </template>
      
      <div v-else class="completion-message">
        <h2>今天沒有待複習單詞</h2>
        <p>稍後再回來學習新的單詞。</p>
      </div>
    </section>
  </main>
</template>
