# 前端开发规范（Vue 3）

## 1. 项目结构

```
frontend/
├── public/
│   └── favicon.ico
├── src/
│   ├── api/
│   │   ├── client.js           # Axios 实例与拦截器
│   │   ├── documents.js        # 文档管理 API
│   │   └── query.js            # 问答检索 API
│   ├── components/
│   │   ├── UploadPanel.vue     # 文件上传面板
│   │   ├── ChatPanel.vue       # 问答对话面板
│   │   ├── DocumentList.vue    # 文档列表
│   │   ├── SourceCard.vue      # 引用来源卡片
│   │   └── AppHeader.vue       # 顶部导航
│   ├── views/
│   │   ├── HomeView.vue        # 首页/仪表盘
│   │   ├── DocumentsView.vue   # 文档管理页
│   │   └── ChatView.vue        # 知识问答页
│   ├── router/
│   │   └── index.js            # Vue Router 配置
│   ├── stores/
│   │   ├── documents.js        # 文档状态（Pinia）
│   │   └── chat.js             # 对话状态（Pinia）
│   ├── composables/
│   │   ├── useUpload.js        # 上传逻辑组合式函数
│   │   └── useChat.js          # 对话逻辑组合式函数
│   ├── utils/
│   │   └── format.js           # 格式化工具
│   ├── App.vue
│   └── main.js
├── index.html
├── vite.config.js
├── package.json
└── .env
```

## 2. 技术栈版本

| 技术 | 版本 | 用途 |
|---|---|---|
| Vue | ^3.4 | 框架核心 |
| Vue Router | ^4.2 | 单页路由 |
| Pinia | ^2.1 | 状态管理 |
| Element Plus | ^2.5 | UI 组件库 |
| Axios | ^1.7 | HTTP 客户端 |
| Vite | ^5.0 | 构建工具 |
| @vitejs/plugin-vue | ^5.0 | Vite Vue 插件 |

## 3. 核心配置

### 3.1 Vite 配置

```javascript
// vite.config.js
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

### 3.2 入口文件

```javascript
// src/main.js
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'

const app = createApp(App)

// 注册所有图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus)

app.mount('#app')
```

### 3.3 路由配置

```javascript
// src/router/index.js
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

## 4. API 层规范

### 4.1 Axios 客户端封装

```javascript
// src/api/client.js
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

### 4.2 API 模块

```javascript
// src/api/documents.js
import client from './client.js'

export const documentsApi = {
  /**
   * 上传 PDF 文档
   * @param {File} file - PDF 文件
   * @param {Function} onProgress - 上传进度回调
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

```javascript
// src/api/query.js
import client from './client.js'

export const queryApi = {
  /**
   * 提交问答查询
   * @param {string} query - 查询文本
   * @param {Object} options - 可选参数
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
   * @param {Function} onMessage - 消息回调
   */
  async askStream(query, onMessage, options = {}) {
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

    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const chunk = decoder.decode(value)
      const lines = chunk.split('\n')

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6)
          if (data === '[DONE]') return
          try {
            const parsed = JSON.parse(data)
            onMessage(parsed)
          } catch {
            onMessage({ content: data })
          }
        }
      }
    }
  }
}
```

## 5. 状态管理规范

### 5.1 文档状态（Pinia）

```javascript
// src/stores/documents.js
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
      documents.value = res.items || []
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
      documents.value.unshift(res)
      return res
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

### 5.2 对话状态

```javascript
// src/stores/chat.js
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useChatStore = defineStore('chat', () => {
  const messages = ref([])
  const isLoading = ref(false)

  const addMessage = (role, content, sources = []) => {
    messages.value.push({
      id: Date.now(),
      role,
      content,
      sources,
      timestamp: new Date().toISOString()
    })
  }

  const clearMessages = () => {
    messages.value = []
  }

  return { messages, isLoading, addMessage, clearMessages }
})
```

## 6. 组件开发规范

### 6.1 单文件组件结构

```vue
<!-- src/components/UploadPanel.vue -->
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
      <el-icon class="upload-icon"><upload-filled /></el-icon>
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
  const isPdf = file.type === 'application/pdf'
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
  ElMessage.success('上传成功')
  emit('success', response)
  setTimeout(() => { progress.value = 0 }, 1000)
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
</style>
```

### 6.2 组件命名规范

- **文件命名**：PascalCase，如 `ChatPanel.vue`
- **组件名**：多词组合，避免单字母，如 `<SourceCard>` 而非 `<Card>`
- **Props 命名**：camelCase，模板中使用 kebab-case，如 `docId` → `:doc-id`

### 6.3 Props 与 Emits 规范

```vue
<script setup>
const props = defineProps({
  docId: {
    type: String,
    required: true
  },
  sources: {
    type: Array,
    default: () => []
  },
  showScore: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits({
  select: (docId) => typeof docId === 'string',
  delete: null
})
</script>
```

## 7. 视图页面规范

### 7.1 文档管理页

```vue
<!-- src/views/DocumentsView.vue -->
<template>
  <div class="documents-view">
    <AppHeader title="文档管理" />

    <div class="content">
      <UploadPanel @success="handleUploadSuccess" />

      <el-table
        v-loading="store.loading"
        :data="store.documents"
        style="width: 100%; margin-top: 24px"
      >
        <el-table-column prop="filename" label="文件名" min-width="200" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_pages" label="页数" width="100" />
        <el-table-column prop="total_chunks" label="分块数" width="100" />
        <el-table-column prop="created_at" label="上传时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              type="danger"
              size="small"
              @click="handleDelete(row.doc_id)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useDocumentStore } from '@/stores/documents.js'
import AppHeader from '@/components/AppHeader.vue'
import UploadPanel from '@/components/UploadPanel.vue'
import { formatDate } from '@/utils/format.js'

const store = useDocumentStore()

const statusMap = {
  pending: { label: '待处理', type: 'info' },
  processing: { label: '处理中', type: 'warning' },
  completed: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' }
}

const statusType = (status) => statusMap[status]?.type || 'info'
const statusLabel = (status) => statusMap[status]?.label || status

const handleUploadSuccess = () => {
  store.fetchDocuments()
}

const handleDelete = async (docId) => {
  try {
    await ElMessageBox.confirm('确定要删除该文档吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await store.removeDocument(docId)
  } catch {
    // 用户取消
  }
}

onMounted(() => {
  store.fetchDocuments()
})
</script>
```

### 7.2 问答页

```vue
<!-- src/views/ChatView.vue -->
<template>
  <div class="chat-view">
    <AppHeader title="知识问答" />

    <div class="chat-container">
      <div class="messages" ref="messagesRef">
        <div
          v-for="msg in chatStore.messages"
          :key="msg.id"
          :class="['message', msg.role]"
        >
          <div class="avatar">
            <el-avatar
              :icon="msg.role === 'user' ? User : ChatDotRound"
              :size="36"
            />
          </div>
          <div class="content">
            <div class="text">{{ msg.content }}</div>
            <SourceCard
              v-if="msg.sources?.length"
              :sources="msg.sources"
            />
          </div>
        </div>

        <div v-if="chatStore.isLoading" class="message assistant">
          <div class="avatar">
            <el-avatar :icon="ChatDotRound" :size="36" />
          </div>
          <div class="content">
            <el-skeleton :rows="2" animated />
          </div>
        </div>
      </div>

      <div class="input-area">
        <el-input
          v-model="inputText"
          type="textarea"
          :rows="3"
          placeholder="请输入您的问题..."
          @keydown.enter.prevent="handleSubmit"
        />
        <el-button
          type="primary"
          :loading="chatStore.isLoading"
          @click="handleSubmit"
        >
          发送
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { User, ChatDotRound } from '@element-plus/icons-vue'
import { useChatStore } from '@/stores/chat.js'
import { queryApi } from '@/api/query.js'
import AppHeader from '@/components/AppHeader.vue'
import SourceCard from '@/components/SourceCard.vue'

const chatStore = useChatStore()
const inputText = ref('')
const messagesRef = ref(null)

const scrollToBottom = async () => {
  await nextTick()
  messagesRef.value.scrollTop = messagesRef.value.scrollHeight
}

const handleSubmit = async () => {
  const question = inputText.value.trim()
  if (!question || chatStore.isLoading) return

  chatStore.addMessage('user', question)
  inputText.value = ''
  chatStore.isLoading = true
  await scrollToBottom()

  try {
    const res = await queryApi.ask(question)
    chatStore.addMessage('assistant', res.answer, res.sources)
  } catch (error) {
    chatStore.addMessage('assistant', '抱歉，请求出错，请稍后重试。')
  } finally {
    chatStore.isLoading = false
    await scrollToBottom()
  }
}
</script>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.chat-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px;
  overflow: hidden;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.message {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.message.user {
  flex-direction: row-reverse;
}

.message.user .content {
  background: var(--el-color-primary-light-9);
}

.content {
  max-width: 70%;
  padding: 12px 16px;
  border-radius: 12px;
  background: var(--el-fill-color-light);
}

.input-area {
  display: flex;
  gap: 12px;
  padding: 16px;
  border-top: 1px solid var(--el-border-color-light);
}
</style>
```

## 8. 组合式函数（Composables）

### 8.1 上传逻辑复用

```javascript
// src/composables/useUpload.js
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

## 9. 环境变量

```
# .env.development
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_APP_TITLE=RAG知识库开发环境

# .env.production
VITE_API_BASE_URL=/api/v1
VITE_APP_TITLE=RAG知识库
```

**规范**：
- 环境变量必须以 `VITE_` 开头才能在客户端代码中访问
- 不要在代码中硬编码 API 地址

## 10. 代码风格

### 10.1 ESLint 配置建议

```javascript
// .eslintrc.js
module.exports = {
  root: true,
  env: { node: true },
  extends: [
    'eslint:recommended',
    'plugin:vue/vue3-recommended'
  ],
  rules: {
    'vue/multi-word-component-names': 'off',
    'vue/require-default-prop': 'off',
    'no-console': process.env.NODE_ENV === 'production' ? 'warn' : 'off'
  }
}
```

### 10.2 命名规范

| 类型 | 规范 | 示例 |
|---|---|---|
| 组件文件 | PascalCase | `ChatPanel.vue` |
| JS 文件 | camelCase | `useUpload.js` |
| 组合式函数 | useXxx | `useChat`, `useUpload` |
| Store | useXxxStore | `useDocumentStore` |
| 常量 | SCREAMING_SNAKE_CASE | `MAX_FILE_SIZE` |
| Props | camelCase | `docId`, `showScore` |

## 11. 性能优化

- **路由懒加载**：所有页面组件使用 `() => import()` 懒加载
- **组件按需引入**：Element Plus 使用自动导入插件
- **图片优化**：使用 WebP 格式，压缩上传文件
- **请求缓存**：GET 请求结果使用 Pinia 缓存，避免重复请求
- **虚拟滚动**：文档列表超过 100 条时使用 `el-table` 虚拟滚动
