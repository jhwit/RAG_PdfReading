import { defineStore } from 'pinia'
import { ref } from 'vue'
import { queryApi } from '@/api/query.js'

export const useChatStore = defineStore('chat', () => {
  const messages = ref([])
  const isLoading = ref(false)
  const streamingContent = ref('')

  const addMessage = (role, content, sources = []) => {
    messages.value.push({
      id: Date.now() + Math.random(),
      role,
      content,
      sources,
      timestamp: new Date().toISOString()
    })
  }

  const updateLastMessage = (content, sources = []) => {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.content = content
      last.sources = sources
    }
  }

  const clearMessages = () => {
    messages.value = []
    streamingContent.value = ''
  }

  const sendMessage = async (question, { topK = 5, stream = false } = {}) => {
    if (!question.trim() || isLoading.value) return

    addMessage('user', question)
    isLoading.value = true

    try {
      if (stream) {
        addMessage('assistant', '', [])
        let fullContent = ''

        await queryApi.askStream(question, (event) => {
          if (event.type === 'chunk') {
            fullContent += event.content || ''
            updateLastMessage(fullContent, [])
          } else if (event.type === 'sources') {
            updateLastMessage(fullContent, event.sources || [])
          } else if (event.type === 'error') {
            updateLastMessage(`错误: ${event.message || '未知错误'}`, [])
          }
        }, { topK })

        if (!fullContent) {
          updateLastMessage('未获取到回答内容', [])
        }
      } else {
        const res = await queryApi.ask(question, { topK })
        const data = res.data || res
        addMessage('assistant', data.answer, data.sources || [])
      }
    } catch (error) {
      addMessage('assistant', `抱歉，请求出错: ${error.message || '请稍后重试'}`, [])
    } finally {
      isLoading.value = false
    }
  }

  return {
    messages,
    isLoading,
    streamingContent,
    addMessage,
    updateLastMessage,
    clearMessages,
    sendMessage
  }
})
