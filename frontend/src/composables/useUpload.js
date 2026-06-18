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
