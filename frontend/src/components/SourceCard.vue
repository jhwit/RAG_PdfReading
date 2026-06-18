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
