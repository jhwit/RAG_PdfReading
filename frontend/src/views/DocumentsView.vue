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
