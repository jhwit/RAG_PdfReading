<template>
  <div class="chat-panel">
    <div class="chat-messages" ref="messagesRef">
      <div v-if="chatStore.messages.length === 0" class="empty-state">
        <el-icon :size="64" color="var(--el-text-color-disabled)"><ChatDotRound /></el-icon>
        <p class="empty-text">开始提问，基于国家标准文档获取答案</p>
        <div class="sample-questions">
          <span class="sample-label">试试这些问题：</span>
          <el-tag
            v-for="q in sampleQuestions"
            :key="q"
            class="sample-tag"
            type="info"
            @click="handleSampleClick(q)"
          >
            {{ q }}
          </el-tag>
        </div>
      </div>

      <div
        v-for="msg in chatStore.messages"
        :key="msg.id"
        :class="['message', msg.role]"
      >
        <div class="message-avatar">
          <el-avatar :size="36" :icon="msg.role === 'user' ? User : ChatDotRound" />
        </div>
        <div class="message-body">
          <div class="message-content">
            <div v-if="msg.role === 'assistant' && !msg.content && chatStore.isLoading" class="thinking">
              <el-skeleton :rows="2" animated />
            </div>
            <div v-else class="message-text">{{ msg.content }}</div>
          </div>
          <SourceCard
            v-if="msg.sources && msg.sources.length > 0"
            :sources="msg.sources"
          />
        </div>
      </div>
    </div>

    <div class="chat-input-area">
      <el-input
        v-model="inputText"
        type="textarea"
        :rows="3"
        placeholder="请输入您的问题（支持中文自然语言查询）..."
        :disabled="chatStore.isLoading"
        resize="none"
        @keydown.enter.exact.prevent="handleSend"
      />
      <div class="input-actions">
        <span class="input-hint">
          {{ chatStore.isLoading ? '回答中...' : 'Enter 发送，Shift+Enter 换行' }}
        </span>
        <el-button
          type="primary"
          :loading="chatStore.isLoading"
          :disabled="!inputText.trim()"
          @click="handleSend"
        >
          <el-icon><Promotion /></el-icon>
          发送
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, watch } from 'vue'
import { User, ChatDotRound, Promotion } from '@element-plus/icons-vue'
import { useChatStore } from '@/stores/chat.js'
import SourceCard from '@/components/SourceCard.vue'

const chatStore = useChatStore()
const inputText = ref('')
const messagesRef = ref(null)

const sampleQuestions = [
  '建筑设计防火规范中关于疏散楼梯的要求是什么？',
  '建筑物抗震设防分类标准有哪些？',
  '电气设备安全间距的要求是什么？'
]

const scrollToBottom = async () => {
  await nextTick()
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

// Auto-scroll when new messages arrive
watch(() => chatStore.messages.length, () => {
  scrollToBottom()
})

// Auto-scroll during streaming (last message content updates)
watch(() => {
  const msgs = chatStore.messages
  if (msgs.length === 0) return ''
  const last = msgs[msgs.length - 1]
  return last.role === 'assistant' ? last.content : ''
}, () => {
  scrollToBottom()
})

const handleSend = async () => {
  const text = inputText.value.trim()
  if (!text || chatStore.isLoading) return

  inputText.value = ''
  await chatStore.sendMessage(text)
  await scrollToBottom()
}

const handleSampleClick = (question) => {
  inputText.value = question
  handleSend()
}
</script>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--el-fill-color-blank);
  border-radius: 8px;
  border: 1px solid var(--el-border-color-light);
  overflow: hidden;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 16px;
  padding: 40px;
}

.empty-text {
  font-size: 15px;
  color: var(--el-text-color-secondary);
  margin: 0;
}

.sample-questions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  justify-content: center;
  margin-top: 8px;
}

.sample-label {
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.sample-tag {
  cursor: pointer;
  transition: all 0.2s;
}

.sample-tag:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.message {
  display: flex;
  gap: 12px;
  max-width: 85%;
}

.message.user {
  flex-direction: row-reverse;
  align-self: flex-end;
}

.message.assistant {
  align-self: flex-start;
}

.message-avatar {
  flex-shrink: 0;
}

.message-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.message-content {
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.7;
  word-break: break-word;
}

.message.user .message-content {
  background: var(--el-color-primary-light-9);
  border-bottom-right-radius: 4px;
}

.message.assistant .message-content {
  background: var(--el-fill-color-light);
  border-bottom-left-radius: 4px;
}

.message-text {
  white-space: pre-wrap;
}

.thinking {
  width: 200px;
}

.chat-input-area {
  padding: 16px 20px;
  border-top: 1px solid var(--el-border-color-light);
  background: var(--el-fill-color-blank);
}

.input-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
}

.input-hint {
  font-size: 12px;
  color: var(--el-text-color-disabled);
}
</style>
