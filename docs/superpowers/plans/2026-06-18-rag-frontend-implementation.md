# RAG 知识库前端 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete Vue 3 frontend for the RAG Knowledge Base system per the 4 spec documents in `docs/`.

**Architecture:** Vue 3 SPA with Element Plus UI. Axios API layer → Pinia stores → Components → Views → Router. All code follows `03-frontend-spec.md` exactly for spec-provided files; designed components follow the same conventions.

**Tech Stack:** Vue 3.4+, Vue Router 4.2+, Pinia 2.1+, Element Plus 2.5+, Axios 1.7+, Vite 5.0+

## Global Constraints

- All components use `<script setup>` syntax
- Component filenames: PascalCase (e.g. `ChatPanel.vue`)
- JS filenames: camelCase (e.g. `useUpload.js`)
- Props declared with `defineProps`, events with `defineEmits`
- Styles use `scoped` attribute
- API base URL from `import.meta.env.VITE_API_BASE_URL`, no hardcoding
- Environment variables must start with `VITE_`
- Routes use lazy loading: `() => import()`

---

### Task 1: Project Scaffolding

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.js`
- Create: `frontend/index.html`
- Create: `frontend/.env`
- Create: `frontend/.env.production`

**Interfaces:**
- Produces: npm project with all dependencies, Vite dev server on port 5173 with `/api` proxy to `localhost:8000`

- [ ] **Step 1: Create package.json**

```json
{
  "name": "rag-knowledge-base-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "vue": "^3.4.0",
    "vue-router": "^4.2.0",
    "pinia": "^2.1.0",
    "element-plus": "^2.5.0",
    "@element-plus/icons-vue": "^2.3.0",
    "axios": "^1.7.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "vite": "^5.0.0"
  }
}
```

- [ ] **Step 2: Create vite.config.js**

```javascript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: true
  }
})
```

- [ ] **Step 3: Create index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>RAG 知识库</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
```

- [ ] **Step 4: Create .env (development)**

```
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_APP_TITLE=RAG知识库开发环境
```

- [ ] **Step 5: Create .env.production**

```
VITE_API_BASE_URL=/api/v1
VITE_APP_TITLE=RAG知识库
```

- [ ] **Step 6: Install dependencies and verify**

```bash
cd frontend && npm install
```

Expected: All packages install without errors.

---

### Task 2: Utility Functions

**Files:**
- Create: `frontend/src/utils/format.js`

**Interfaces:**
- Produces: `formatDate(isoString)` → formatted Chinese date string, `formatFileSize(bytes)` → human-readable size, `statusLabel(status)` → Chinese status text, `statusType(status)` → Element Plus tag type

- [ ] **Step 1: Create format.js**

```javascript
/**
 * 格式化工具函数
 */

/**
 * 格式化 ISO 日期字符串为中文格式
 * @param {string} isoString - ISO 8601 日期字符串
 * @returns {string} 格式化后的日期
 */
export function formatDate(isoString) {
  if (!isoString) return '-'
  const date = new Date(isoString)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}`
}

/**
 * 格式化文件大小
 * @param {number} bytes - 字节数
 * @returns {string}
 */
export function formatFileSize(bytes) {
  if (!bytes || bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const k = 1024
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + units[i]
}

/**
 * 文档状态映射
 */
const STATUS_MAP = {
  pending: { label: '待处理', type: 'info' },
  processing: { label: '处理中', type: 'warning' },
  completed: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' }
}

/**
 * 获取状态中文标签
 * @param {string} status
 * @returns {string}
 */
export function statusLabel(status) {
  return STATUS_MAP[status]?.label || status || '-'
}

/**
 * 获取状态对应的 Element Plus Tag 类型
 * @param {string} status
 * @returns {string}
 */
export function statusType(status) {
  return STATUS_MAP[status]?.type || 'info'
}

/**
 * 截断文本
 * @param {string} text
 * @param {number} maxLength
 * @returns {string}
 */
export function truncateText(text, maxLength = 100) {
  if (!text || text.length <= maxLength) return text || ''
  return text.slice(0, maxLength) + '...'
}
```

---

### Task 3: API Layer

**Files:**
- Create: `frontend/src/api/client.js`
- Create: `frontend/src/api/documents.js`
- Create: `frontend/src/api/query.js`

**Interfaces:**
- Produces:
  - `client` — configured Axios instance (baseURL from env, 30s timeout, request/response interceptors)
  - `documentsApi.upload(file, onProgress)` → upload PDF
  - `documentsApi.list()` → get document list
  - `documentsApi.getDetail(docId)` → get document detail
  - `documentsApi.delete(docId)` → delete document
  - `documentsApi.getStatus(docId)` → get processing status
  - `queryApi.ask(query, options)` → submit question
  - `queryApi.askStream(query, onMessage, options)` → SSE streaming question

- [ ] **Step 1: Create client.js** (from `03-frontend-spec.md` §4.1)

```javascript
import axios from 'axios'
import { ElMessage } from 'element-plus'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
client.interceptors.request.use(
  config => {
    console.log(`[API] ${config.method.toUpperCase()} ${config.url}`)
    return config
  },
  error => Promise.reject(error)
)

// 响应拦截器
client.interceptors.response.use(
  response => response.data,
  error => {
    const status = error.response?.status
    const data = error.response?.data
    const message = data?.message || error.message || '请求失败'

    if (status === 401) {
      ElMessage.error('未授权，请重新登录')
    } else if (status === 403) {
      ElMessage.error('权限不足')
    } else if (status === 404) {
      ElMessage.error('资源不存在')
    } else if (status >= 500) {
      ElMessage.error('服务器错误，请稍后重试')
    } else {
      ElMessage.error(message)
    }

    return Promise.reject(error)
  }
)

export default client
```

- [ ] **Step 2: Create documents.js** (from `03-frontend-spec.md` §4.2, extended with getDetail from `04-api-spec.md` §2 GET /documents/{doc_id})

```javascript
import client from './client.js'

export const documentsApi = {
  /**
   * 上传 PDF 文档
   * @param {File} file - PDF 文件
   * @param {Function} onProgress - 上传进度回调 (percent: number) => void
   * @returns {Promise}
   */
  upload(file, onProgress) {
    const formData = new FormData()
    formData.append('file', file)
    return client.post('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (event) => {
        const percent = Math.round((event.loaded * 100) / event.total)
        onProgress?.(percent)
      }
    })
  },

  /** 获取文档列表 */
  list() {
    return client.get('/documents')
  },

  /** 获取文档详情 */
  getDetail(docId) {
    return client.get(`/documents/${docId}`)
  },

  /** 删除文档 */
  delete(docId) {
    return client.delete(`/documents/${docId}`)
  },

  /** 获取文档处理状态 */
  getStatus(docId) {
    return client.get(`/documents/${docId}/status`)
  }
}
```

- [ ] **Step 3: Create query.js** (from `03-frontend-spec.md` §4.2, extended with SSE streaming from `04-api-spec.md` §3 POST /query/stream)

```javascript
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
```

---

### Task 4: Pinia Stores

**Files:**
- Create: `frontend/src/stores/documents.js`
- Create: `frontend/src/stores/chat.js`

**Interfaces:**
- Produces:
  - `useDocumentStore()` — `{ documents, loading, uploadProgress, completedDocs, processingDocs, docCount, fetchDocuments(), uploadDocument(file), removeDocument(docId) }`
  - `useChatStore()` — `{ messages, isLoading, addMessage(role, content, sources), clearMessages() }`

- [ ] **Step 1: Create documents.js store** (from `03-frontend-spec.md` §5.1)

```javascript
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { documentsApi } from '@/api/documents.js'

export const useDocumentStore = defineStore('documents', () => {
  // State
  const documents = ref([])
  const loading = ref(false)
  const uploadProgress = ref(0)

  // Getters
  const completedDocs = computed(() =>
    documents.value.filter(d => d.status === 'completed')
  )

  const processingDocs = computed(() =>
    documents.value.filter(d => d.status === 'processing')
  )

  const docCount = computed(() => documents.value.length)

  // Actions
  const fetchDocuments = async () => {
    loading.value = true
    try {
      const res = await documentsApi.list()
      // API returns { code, message, data: { items, total } }
      documents.value = res.data?.items || res.items || []
    } catch (error) {
      console.error('Failed to fetch documents:', error)
    } finally {
      loading.value = false
    }
  }

  const uploadDocument = async (file) => {
    uploadProgress.value = 0
    try {
      const res = await documentsApi.upload(file, (percent) => {
        uploadProgress.value = percent
      })
      // API returns { code, message, data: { doc_id, filename, status, ... } }
      const doc = res.data || res
      documents.value.unshift(doc)
      return doc
    } finally {
      uploadProgress.value = 0
    }
  }

  const removeDocument = async (docId) => {
    await documentsApi.delete(docId)
    documents.value = documents.value.filter(d => d.doc_id !== docId)
  }

  return {
    documents,
    loading,
    uploadProgress,
    completedDocs,
    processingDocs,
    docCount,
    fetchDocuments,
    uploadDocument,
    removeDocument
  }
})
```

- [ ] **Step 2: Create chat.js store** (from `03-frontend-spec.md` §5.2, extended with streaming support)

```javascript
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
```

---

### Task 5: Base Components

**Files:**
- Create: `frontend/src/components/AppHeader.vue`
- Create: `frontend/src/components/UploadPanel.vue`
- Create: `frontend/src/components/SourceCard.vue`
- Create: `frontend/src/components/DocumentList.vue`

**Interfaces:**
- Consumes: `useRouter()` from vue-router, format utilities
- Produces:
  - `<AppHeader title="..." />` — top navigation bar with menu
  - `<UploadPanel uploadAction="..." @success @error />` — drag-and-drop PDF upload
  - `<SourceCard :sources="[...]" />` — source reference cards
  - `<DocumentList :documents="[...]" :loading="false" @delete="docId" />` — document table with actions

- [ ] **Step 1: Create AppHeader.vue**

```vue
<template>
  <el-header class="app-header">
    <div class="header-left">
      <el-icon :size="24" class="logo-icon"><Reading /></el-icon>
      <span class="title">{{ title || 'RAG 知识库' }}</span>
    </div>
    <el-menu
      :default-active="activeMenu"
      mode="horizontal"
      :ellipsis="false"
      router
      class="header-menu"
    >
      <el-menu-item index="/">
        <el-icon><HomeFilled /></el-icon>
        <span>首页</span>
      </el-menu-item>
      <el-menu-item index="/documents">
        <el-icon><Document /></el-icon>
        <span>文档管理</span>
      </el-menu-item>
      <el-menu-item index="/chat">
        <el-icon><ChatDotRound /></el-icon>
        <span>知识问答</span>
      </el-menu-item>
    </el-menu>
    <div class="header-right">
      <el-tag size="small" type="info">v0.1.0</el-tag>
    </div>
  </el-header>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { HomeFilled, Document, ChatDotRound, Reading } from '@element-plus/icons-vue'

defineProps({
  title: {
    type: String,
    default: ''
  }
})

const route = useRoute()
const activeMenu = computed(() => route.path)
</script>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #fff;
  border-bottom: 1px solid var(--el-border-color-light);
  height: 60px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 180px;
}

.logo-icon {
  color: var(--el-color-primary);
}

.title {
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
}

.header-menu {
  border-bottom: none !important;
  flex: 1;
  justify-content: center;
}

.header-menu .el-menu-item {
  border-bottom: none;
}

.header-right {
  min-width: 80px;
  display: flex;
  justify-content: flex-end;
}
</style>
```

- [ ] **Step 2: Create UploadPanel.vue** (from `03-frontend-spec.md` §6.1)

```vue
<template>
  <div class="upload-panel">
    <el-upload
      drag
      :action="uploadAction"
      accept=".pdf"
      :before-upload="handleBeforeUpload"
      :on-progress="handleProgress"
      :on-success="handleSuccess"
      :on-error="handleError"
      :show-file-list="false"
    >
      <el-icon class="upload-icon"><UploadFilled /></el-icon>
      <div class="upload-text">
        拖拽文件到此处或 <em>点击上传</em>
      </div>
      <template #tip>
        <div class="upload-tip">
          仅支持 PDF 文件，单个文件不超过 50MB
        </div>
      </template>
    </el-upload>

    <el-progress
      v-if="progress > 0 && progress < 100"
      :percentage="progress"
      :stroke-width="16"
      status="active"
      class="upload-progress"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'

const props = defineProps({
  uploadAction: {
    type: String,
    default: '/api/v1/documents/upload'
  }
})

const emit = defineEmits(['success', 'error'])

const progress = ref(0)

const handleBeforeUpload = (file) => {
  const isPdf = file.type === 'application/pdf' || file.name.endsWith('.pdf')
  const isLt50M = file.size / 1024 / 1024 < 50

  if (!isPdf) {
    ElMessage.error('仅支持 PDF 文件')
    return false
  }
  if (!isLt50M) {
    ElMessage.error('文件大小不能超过 50MB')
    return false
  }

  progress.value = 0
  return true
}

const handleProgress = (event) => {
  progress.value = Math.round((event.loaded * 100) / event.total)
}

const handleSuccess = (response) => {
  progress.value = 100
  ElMessage.success('上传成功，文档已加入处理队列')
  emit('success', response)
  setTimeout(() => { progress.value = 0 }, 1500)
}

const handleError = (error) => {
  progress.value = 0
  const message = error.message || '上传失败'
  ElMessage.error(message)
  emit('error', error)
}
</script>

<style scoped>
.upload-panel {
  padding: 24px;
  background: var(--el-fill-color-blank);
  border-radius: 8px;
  border: 1px solid var(--el-border-color-light);
}

.upload-icon {
  font-size: 48px;
  color: var(--el-color-primary);
  margin-bottom: 16px;
}

.upload-text {
  font-size: 16px;
  color: var(--el-text-color-regular);
}

.upload-text em {
  color: var(--el-color-primary);
  font-style: normal;
  cursor: pointer;
}

.upload-tip {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.upload-progress {
  margin-top: 16px;
}
</style>
```

- [ ] **Step 3: Create SourceCard.vue**

```vue
<template>
  <div class="source-card">
    <div class="source-header">
      <el-icon :size="14"><Link /></el-icon>
      <span class="source-label">引用来源</span>
    </div>
    <div class="source-list">
      <div
        v-for="(source, index) in sources"
        :key="index"
        class="source-item"
      >
        <div class="source-main">
          <el-icon :size="14" class="source-doc-icon"><Document /></el-icon>
          <span class="source-name">{{ source.doc_name }}</span>
          <el-tag size="small" type="info" class="source-page">
            第 {{ source.page }} 页
          </el-tag>
        </div>
        <div class="source-meta">
          <span class="source-score">
            相似度: {{ (source.score * 100).toFixed(1) }}%
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Link, Document } from '@element-plus/icons-vue'

defineProps({
  sources: {
    type: Array,
    default: () => []
  }
})
</script>

<style scoped>
.source-card {
  margin-top: 12px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
}

.source-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  color: var(--el-text-color-secondary);
}

.source-label {
  font-size: 12px;
  font-weight: 500;
}

.source-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.source-item {
  padding: 8px 12px;
  background: var(--el-fill-color-blank);
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
}

.source-main {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.source-doc-icon {
  color: var(--el-color-primary);
  flex-shrink: 0;
}

.source-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-page {
  flex-shrink: 0;
}

.source-meta {
  padding-left: 20px;
}

.source-score {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
</style>
```

- [ ] **Step 4: Create DocumentList.vue**

```vue
<template>
  <div class="document-list">
    <el-table
      v-loading="loading"
      :data="documents"
      style="width: 100%"
      empty-text="暂无文档"
      stripe
    >
      <el-table-column prop="filename" label="文件名" min-width="220">
        <template #default="{ row }">
          <div class="doc-filename">
            <el-icon :size="16" color="var(--el-color-primary)"><Document /></el-icon>
            <span>{{ row.filename }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="total_pages" label="页数" width="80" />
      <el-table-column prop="total_chunks" label="分块数" width="80" />
      <el-table-column prop="created_at" label="上传时间" width="170">
        <template #default="{ row }">
          {{ formatDate(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-popconfirm
            title="确定要删除该文档吗？"
            confirm-button-text="确定"
            cancel-button-text="取消"
            @confirm="handleDelete(row.doc_id)"
          >
            <template #reference>
              <el-button type="danger" size="small" text>
                删除
              </el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { Document } from '@element-plus/icons-vue'
import { formatDate, statusLabel, statusType } from '@/utils/format.js'

defineProps({
  documents: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['delete'])

const handleDelete = (docId) => {
  emit('delete', docId)
}
</script>

<style scoped>
.document-list {
  margin-top: 20px;
}

.doc-filename {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
```

---

### Task 6: Chat Component

**Files:**
- Create: `frontend/src/components/ChatPanel.vue`

**Interfaces:**
- Consumes: `useChatStore()`, `SourceCard` component
- Produces: `<ChatPanel />` — self-contained chat interface with message list, input area, and streaming support

- [ ] **Step 1: Create ChatPanel.vue**

```vue
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

// Auto-scroll when messages change
watch(() => chatStore.messages.length, () => {
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
```

---

### Task 7: Composables

**Files:**
- Create: `frontend/src/composables/useUpload.js`

**Interfaces:**
- Produces: `useUpload()` — `{ progress, uploading, error, upload(file) }`

- [ ] **Step 1: Create useUpload.js** (from `03-frontend-spec.md` §8.1)

```javascript
import { ref } from 'vue'
import { documentsApi } from '@/api/documents.js'

export function useUpload() {
  const progress = ref(0)
  const uploading = ref(false)
  const error = ref(null)

  const upload = async (file) => {
    uploading.value = true
    progress.value = 0
    error.value = null

    try {
      const res = await documentsApi.upload(file, (percent) => {
        progress.value = percent
      })
      return res
    } catch (err) {
      error.value = err
      throw err
    } finally {
      uploading.value = false
    }
  }

  return { progress, uploading, error, upload }
}
```

---

### Task 8: View Pages

**Files:**
- Create: `frontend/src/views/HomeView.vue`
- Create: `frontend/src/views/DocumentsView.vue`
- Create: `frontend/src/views/ChatView.vue`

**Interfaces:**
- Consumes: Pinia stores, all components, router
- Produces: Three route-level page components with `<AppHeader>` + content

- [ ] **Step 1: Create HomeView.vue**

```vue
<template>
  <div class="home-view">
    <AppHeader title="RAG 知识库" />

    <div class="home-content">
      <div class="welcome-section">
        <h1 class="welcome-title">国家标准知识库</h1>
        <p class="welcome-desc">
          基于 RAG（检索增强生成）技术的智能文档问答系统。上传国家标准 PDF 文档，
          系统自动解析并建立语义索引，支持自然语言查询，精准定位规范条文。
        </p>
      </div>

      <div class="stats-row">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-inner">
            <el-icon :size="32" color="var(--el-color-primary)"><Document /></el-icon>
            <div class="stat-info">
              <div class="stat-number">{{ store.docCount }}</div>
              <div class="stat-label">文档总数</div>
            </div>
          </div>
        </el-card>

        <el-card class="stat-card" shadow="hover">
          <div class="stat-inner">
            <el-icon :size="32" color="var(--el-color-success)"><CircleCheckFilled /></el-icon>
            <div class="stat-info">
              <div class="stat-number">{{ store.completedDocs.length }}</div>
              <div class="stat-label">已处理</div>
            </div>
          </div>
        </el-card>

        <el-card class="stat-card" shadow="hover">
          <div class="stat-inner">
            <el-icon :size="32" color="var(--el-color-warning)"><Loading /></el-icon>
            <div class="stat-info">
              <div class="stat-number">{{ store.processingDocs.length }}</div>
              <div class="stat-label">处理中</div>
            </div>
          </div>
        </el-card>
      </div>

      <div class="actions-row">
        <el-card class="action-card" shadow="hover" @click="$router.push('/documents')">
          <el-icon :size="40" color="var(--el-color-primary)"><Upload /></el-icon>
          <h3>文档管理</h3>
          <p>上传和管理国家标准 PDF 文档，查看处理状态</p>
        </el-card>

        <el-card class="action-card" shadow="hover" @click="$router.push('/chat')">
          <el-icon :size="40" color="var(--el-color-success)"><ChatDotRound /></el-icon>
          <h3>知识问答</h3>
          <p>基于已索引的文档进行自然语言问答，获取精准答案</p>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { Document, CircleCheckFilled, Loading, Upload, ChatDotRound } from '@element-plus/icons-vue'
import { useDocumentStore } from '@/stores/documents.js'
import AppHeader from '@/components/AppHeader.vue'

const store = useDocumentStore()

onMounted(() => {
  store.fetchDocuments()
})
</script>

<style scoped>
.home-view {
  min-height: 100vh;
  background: var(--el-fill-color-lighter);
}

.home-content {
  max-width: 960px;
  margin: 0 auto;
  padding: 40px 24px;
}

.welcome-section {
  text-align: center;
  margin-bottom: 40px;
}

.welcome-title {
  font-size: 32px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  margin: 0 0 12px;
}

.welcome-desc {
  font-size: 15px;
  color: var(--el-text-color-secondary);
  line-height: 1.8;
  max-width: 640px;
  margin: 0 auto;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 32px;
}

.stat-inner {
  display: flex;
  align-items: center;
  gap: 16px;
}

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-number {
  font-size: 28px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  line-height: 1.2;
}

.stat-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.actions-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.action-card {
  cursor: pointer;
  text-align: center;
  padding: 24px;
  transition: transform 0.2s, box-shadow 0.2s;
}

.action-card:hover {
  transform: translateY(-2px);
}

.action-card h3 {
  margin: 12px 0 8px;
  font-size: 18px;
  color: var(--el-text-color-primary);
}

.action-card p {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
</style>
```

- [ ] **Step 2: Create DocumentsView.vue** (from `03-frontend-spec.md` §7.1, adapted to use DocumentList component)

```vue
<template>
  <div class="documents-view">
    <AppHeader title="文档管理" />

    <div class="documents-content">
      <UploadPanel @success="handleUploadSuccess" />

      <DocumentList
        :documents="store.documents"
        :loading="store.loading"
        @delete="handleDelete"
      />
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useDocumentStore } from '@/stores/documents.js'
import AppHeader from '@/components/AppHeader.vue'
import UploadPanel from '@/components/UploadPanel.vue'
import DocumentList from '@/components/DocumentList.vue'

const store = useDocumentStore()

const handleUploadSuccess = () => {
  store.fetchDocuments()
}

const handleDelete = async (docId) => {
  try {
    await store.removeDocument(docId)
    ElMessage.success('文档已删除')
  } catch (error) {
    ElMessage.error('删除失败')
  }
}

onMounted(() => {
  store.fetchDocuments()
})
</script>

<style scoped>
.documents-view {
  min-height: 100vh;
  background: var(--el-fill-color-lighter);
}

.documents-content {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px;
}
</style>
```

- [ ] **Step 3: Create ChatView.vue** (from `03-frontend-spec.md` §7.2, adapted to use ChatPanel component)

```vue
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
```

---

### Task 9: Router & App Shell

**Files:**
- Create: `frontend/src/router/index.js`
- Create: `frontend/src/App.vue`

**Interfaces:**
- Produces:
  - Router with 3 routes (`/`, `/documents`, `/chat`), lazy-loaded, title management
  - `<App>` root component with `<router-view>`

- [ ] **Step 1: Create router/index.js** (from `03-frontend-spec.md` §3.3)

```javascript
import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/HomeView.vue'),
    meta: { title: '首页' }
  },
  {
    path: '/documents',
    name: 'Documents',
    component: () => import('@/views/DocumentsView.vue'),
    meta: { title: '文档管理' }
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('@/views/ChatView.vue'),
    meta: { title: '知识问答' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  document.title = to.meta.title ? `${to.meta.title} - RAG知识库` : 'RAG知识库'
  next()
})

export default router
```

- [ ] **Step 2: Create App.vue**

```vue
<template>
  <router-view />
</template>

<script setup>
// Root component — each view manages its own layout including AppHeader
</script>

<style>
/* Global reset */
*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html, body {
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',
    'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Helvetica, Arial,
    sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: var(--el-text-color-primary);
}

#app {
  height: 100%;
}
</style>
```

---

### Task 10: Entry Point

**Files:**
- Create: `frontend/src/main.js`

**Interfaces:**
- Produces: Vue app instance, mounted to `#app`, with Pinia + Router + Element Plus installed

- [ ] **Step 1: Create main.js** (from `03-frontend-spec.md` §3.2)

```javascript
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'

const app = createApp(App)

// 注册所有 Element Plus 图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })

app.mount('#app')
```

- [ ] **Step 2: Verify Vite dev server starts**

```bash
cd frontend && npx vite --host 0.0.0.0
```

Expected: Dev server starts on port 5173, no compilation errors.

---

### Task 11: Integration Verification

**Files:**
- None (verification only)

- [ ] **Step 1: Run production build**

```bash
cd frontend && npm run build
```

Expected: Build succeeds, output in `frontend/dist/`. No TypeScript/Vue/SFC compilation errors. All chunks generated.

- [ ] **Step 2: Verify file structure matches spec**

```bash
ls -R frontend/src/
```

Expected output matches the structure defined in `03-frontend-spec.md` §1:

```
src/
├── api/
│   ├── client.js
│   ├── documents.js
│   └── query.js
├── components/
│   ├── AppHeader.vue
│   ├── ChatPanel.vue
│   ├── DocumentList.vue
│   ├── SourceCard.vue
│   └── UploadPanel.vue
├── composables/
│   └── useUpload.js
├── router/
│   └── index.js
├── stores/
│   ├── chat.js
│   └── documents.js
├── utils/
│   └── format.js
├── views/
│   ├── ChatView.vue
│   ├── DocumentsView.vue
│   └── HomeView.vue
├── App.vue
└── main.js
```

---
