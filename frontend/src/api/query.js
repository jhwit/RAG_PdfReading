import client from './client.js'

export const queryApi = {
  /**
   * 提交问答查询
   * @param {string} query - 查询文本
   * @param {Object} options - 可选参数
   * @param {number} options.topK - 检索数量 (1-20, 默认 5)
   * @param {string[]} options.filterDocIds - 限定文档范围
   * @returns {Promise}
   */
  ask(query, options = {}) {
    const { topK = 5, filterDocIds = null } = options
    return client.post('/query', {
      query,
      top_k: topK,
      filter_doc_ids: filterDocIds
    })
  },

  /**
   * 流式问答（SSE）
   * @param {string} query - 查询文本
   * @param {Function} onEvent - 事件回调 (event: object) => void
   *   event.type: 'start' | 'chunk' | 'sources' | 'end' | 'error'
   * @param {Object} options - 可选参数
   * @returns {Promise}
   */
  async askStream(query, onEvent, options = {}) {
    const response = await fetch(
      `${client.defaults.baseURL}/query/stream`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          query,
          top_k: options.topK || 5,
          filter_doc_ids: options.filterDocIds || null
        })
      }
    )

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.message || `HTTP ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      // 保留最后一个可能不完整的行
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6)
          if (data === '[DONE]') return
          try {
            const parsed = JSON.parse(data)
            onEvent(parsed)
          } catch {
            // 非 JSON 数据作为 content 处理
            onEvent({ type: 'chunk', content: data })
          }
        }
      }
    }
  }
}
