<template>
  <div class="upload-panel">
    <el-upload
      drag
      accept=".pdf"
      :http-request="handleHttpRequest"
      :before-upload="handleBeforeUpload"
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

    <el-progress
      v-if="progress === 100"
      :percentage="100"
      :stroke-width="16"
      status="success"
      class="upload-progress"
    />
  </div>
</template>

<script setup>
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { useUpload } from '@/composables/useUpload.js'

const emit = defineEmits(['success', 'error'])

const { progress, uploading: _uploading, upload } = useUpload()

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

  return true
}

const handleHttpRequest = async (options) => {
  const { file, onSuccess, onError } = options
  try {
    const result = await upload(file)
    ElMessage.success('上传成功，文档已加入处理队列')
    onSuccess(result)
    emit('success', result)
    // Reset progress after 1.5s delay so the user can see the 100% state
    setTimeout(() => { progress.value = 0 }, 1500)
  } catch (error) {
    // Error messaging is handled by the Axios response interceptor
    const message = error.response?.data?.message || error.message || '上传失败'
    ElMessage.error(message)
    onError(error)
    emit('error', error)
  }
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
