import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { documentsApi } from '@/api/documents.js'

export const useDocumentStore = defineStore('documents', () => {
  // State
  const documents = ref([])
  const loading = ref(false)
  const fetchError = ref('')
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
    fetchError.value = ''
    try {
      const res = await documentsApi.list()
      // API returns { code, message, data: { items, total } }
      documents.value = res.data?.items || res.items || []
    } catch (error) {
      fetchError.value = error.message || '获取文档列表失败'
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

  const fetchChunks = async (docId) => {
    const res = await documentsApi.getChunks(docId)
    return res.data || []
  }

  return {
    documents,
    loading,
    fetchError,
    uploadProgress,
    completedDocs,
    processingDocs,
    docCount,
    fetchDocuments,
    uploadDocument,
    removeDocument,
    fetchChunks
  }
})
