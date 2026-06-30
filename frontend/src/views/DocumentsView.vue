<template>
  <div class="documents-view">
    <AppHeader title="文档管理" />

    <div class="documents-content">
      <UploadPanel @success="handleUploadSuccess" />

      <DocumentList
        :documents="store.documents"
        :loading="store.loading"
        @delete="handleDelete"
        @view-chunks="handleViewChunks"
      />
    </div>

    <ChunkViewer
      v-model="chunkViewerVisible"
      :doc-id="selectedDocId"
      :doc-name="selectedDocName"
    />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useDocumentStore } from '@/stores/documents.js'
import AppHeader from '@/components/AppHeader.vue'
import UploadPanel from '@/components/UploadPanel.vue'
import DocumentList from '@/components/DocumentList.vue'
import ChunkViewer from '@/components/ChunkViewer.vue'

const store = useDocumentStore()

const chunkViewerVisible = ref(false)
const selectedDocId = ref('')
const selectedDocName = ref('')

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

const handleViewChunks = (row) => {
  selectedDocId.value = row.doc_id
  selectedDocName.value = row.filename
  chunkViewerVisible.value = true
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
