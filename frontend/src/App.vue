<script setup>
import locale from '@arco-design/web-vue/es/locale/lang/zh-tw'
</script>

<template>
  <a-config-provider :locale="locale">
    <RouterView />
  </a-config-provider>
</template>
