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

  progress.value = 0
  return true
}

const handleProgress = (event) => {
  progress.value = Math.round((event.loaded * 100) / event.total)
}

const handleSuccess = (response) => {
  progress.value = 100
  ElMessage.success('上传成功，文档已加入处理队列')
  emit('success', response)
  setTimeout(() => { progress.value = 0 }, 1500)
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
