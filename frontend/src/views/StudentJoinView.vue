<script setup>
import { ref } from 'vue'

const sessionCode = ref('')
</script>

<template>
  <main class="auth-shell">
    <section class="auth-card student-card">
      <div class="brand-mark student-mark">答</div>
      <p class="eyebrow">ENGLISH MATH CLASSROOM</p>
      <h1>加入答題</h1>
      <p class="muted">請使用手機掃描老師展示的 QR Code，或輸入課堂代碼。</p>
      <form class="form-stack" @submit.prevent>
        <label>
          <span>課堂代碼</span>
          <input v-model="sessionCode" inputmode="numeric" placeholder="例如：123456" />
        </label>
        <button class="primary-button" type="submit">加入課堂</button>
      </form>
      <RouterLink class="back-link" to="/login">返回老師登入</RouterLink>
    </section>
  </main>
</template>
