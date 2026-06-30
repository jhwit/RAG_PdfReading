<template>
  <el-dialog
    v-model="visible"
    :title="`文档分块 — ${docName}`"
    width="800px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <div v-loading="loading" class="chunk-viewer">
      <el-empty v-if="!loading && chunks.length === 0" description="暂无分块数据" />

      <div v-else class="chunk-list">
        <div
          v-for="(chunk, index) in chunks"
          :key="chunk.id"
          class="chunk-item"
        >
          <div class="chunk-header">
            <el-tag size="small" type="primary">#{{ chunk.chunk_index ?? index }}</el-tag>
            <el-tag size="small" type="info">第 {{ chunk.page ?? '?' }} 页</el-tag>
          </div>
          <div class="chunk-content">
            {{ chunk.content }}
          </div>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useDocumentStore } from '@/stores/documents.js'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  docId: {
    type: String,
    default: ''
  },
  docName: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:modelValue'])

const store = useDocumentStore()

const visible = ref(false)
const loading = ref(false)
const chunks = ref([])

watch(() => props.modelValue, (val) => {
  visible.value = val
  if (val && props.docId) {
    loadChunks()
  }
})

watch(visible, (val) => {
  emit('update:modelValue', val)
  if (!val) {
    chunks.value = []
  }
})

const loadChunks = async () => {
  loading.value = true
  try {
    chunks.value = await store.fetchChunks(props.docId)
  } catch (error) {
    ElMessage.error('获取分块内容失败')
    chunks.value = []
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.chunk-viewer {
  max-height: 60vh;
  overflow-y: auto;
}

.chunk-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chunk-item {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 12px 16px;
  background: var(--el-fill-color-lighter);
}

.chunk-header {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;
}

.chunk-content {
  font-size: 14px;
  line-height: 1.7;
  color: var(--el-text-color-primary);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
