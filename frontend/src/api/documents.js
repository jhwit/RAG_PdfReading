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
  },

  /** 获取文档分块内容 */
  getChunks(docId) {
    return client.get(`/documents/${docId}/chunks`)
  }
}
