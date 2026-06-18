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
