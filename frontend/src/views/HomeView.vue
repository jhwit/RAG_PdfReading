<template>
  <div class="home-view">
    <AppHeader title="RAG 知识库" />

    <div class="home-content">
      <div class="welcome-section">
        <h1 class="welcome-title">国家标准知识库</h1>
        <p class="welcome-desc">
          基于 RAG（检索增强生成）技术的智能文档问答系统。上传国家标准 PDF 文档，
          系统自动解析并建立语义索引，支持自然语言查询，精准定位规范条文。
        </p>
      </div>

      <div class="stats-row">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-inner">
            <el-icon :size="32" color="var(--el-color-primary)"><Document /></el-icon>
            <div class="stat-info">
              <div class="stat-number">{{ store.docCount }}</div>
              <div class="stat-label">文档总数</div>
            </div>
          </div>
        </el-card>

        <el-card class="stat-card" shadow="hover">
          <div class="stat-inner">
            <el-icon :size="32" color="var(--el-color-success)"><CircleCheckFilled /></el-icon>
            <div class="stat-info">
              <div class="stat-number">{{ store.completedDocs.length }}</div>
              <div class="stat-label">已处理</div>
            </div>
          </div>
        </el-card>

        <el-card class="stat-card" shadow="hover">
          <div class="stat-inner">
            <el-icon :size="32" color="var(--el-color-warning)"><Loading /></el-icon>
            <div class="stat-info">
              <div class="stat-number">{{ store.processingDocs.length }}</div>
              <div class="stat-label">处理中</div>
            </div>
          </div>
        </el-card>
      </div>

      <div class="actions-row">
        <el-card class="action-card" shadow="hover" @click="$router.push('/documents')">
          <el-icon :size="40" color="var(--el-color-primary)"><Upload /></el-icon>
          <h3>文档管理</h3>
          <p>上传和管理国家标准 PDF 文档，查看处理状态</p>
        </el-card>

        <el-card class="action-card" shadow="hover" @click="$router.push('/chat')">
          <el-icon :size="40" color="var(--el-color-success)"><ChatDotRound /></el-icon>
          <h3>知识问答</h3>
          <p>基于已索引的文档进行自然语言问答，获取精准答案</p>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { Document, CircleCheckFilled, Loading, Upload, ChatDotRound } from '@element-plus/icons-vue'
import { useDocumentStore } from '@/stores/documents.js'
import AppHeader from '@/components/AppHeader.vue'

const store = useDocumentStore()

onMounted(() => {
  store.fetchDocuments()
})
</script>

<style scoped>
.home-view {
  min-height: 100vh;
  background: var(--el-fill-color-lighter);
}

.home-content {
  max-width: 960px;
  margin: 0 auto;
  padding: 40px 24px;
}

.welcome-section {
  text-align: center;
  margin-bottom: 40px;
}

.welcome-title {
  font-size: 32px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  margin: 0 0 12px;
}

.welcome-desc {
  font-size: 15px;
  color: var(--el-text-color-secondary);
  line-height: 1.8;
  max-width: 640px;
  margin: 0 auto;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 32px;
}

.stat-inner {
  display: flex;
  align-items: center;
  gap: 16px;
}

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-number {
  font-size: 28px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  line-height: 1.2;
}

.stat-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.actions-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.action-card {
  cursor: pointer;
  text-align: center;
  padding: 24px;
  transition: transform 0.2s, box-shadow 0.2s;
}

.action-card:hover {
  transform: translateY(-2px);
}

.action-card h3 {
  margin: 12px 0 8px;
  font-size: 18px;
  color: var(--el-text-color-primary);
}

.action-card p {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
</style>
