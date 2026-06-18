<template>
  <div class="chat-view">
    <AppHeader title="知识问答" />

    <div class="chat-content">
      <ChatPanel />
    </div>
  </div>
</template>

<script setup>
import AppHeader from '@/components/AppHeader.vue'
import ChatPanel from '@/components/ChatPanel.vue'
</script>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--el-fill-color-lighter);
}

.chat-content {
  flex: 1;
  padding: 24px;
  overflow: hidden;
  max-width: 1100px;
  width: 100%;
  margin: 0 auto;
}
</style>
