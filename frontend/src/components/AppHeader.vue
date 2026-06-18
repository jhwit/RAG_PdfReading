<template>
  <el-header class="app-header">
    <div class="header-left">
      <el-icon :size="24" class="logo-icon"><Reading /></el-icon>
      <span class="title">{{ title || 'RAG 知识库' }}</span>
    </div>
    <el-menu
      :default-active="activeMenu"
      mode="horizontal"
      :ellipsis="false"
      router
      class="header-menu"
    >
      <el-menu-item index="/">
        <el-icon><HomeFilled /></el-icon>
        <span>首页</span>
      </el-menu-item>
      <el-menu-item index="/documents">
        <el-icon><Document /></el-icon>
        <span>文档管理</span>
      </el-menu-item>
      <el-menu-item index="/chat">
        <el-icon><ChatDotRound /></el-icon>
        <span>知识问答</span>
      </el-menu-item>
    </el-menu>
    <div class="header-right">
      <el-tag size="small" type="info">v0.1.0</el-tag>
    </div>
  </el-header>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { HomeFilled, Document, ChatDotRound, Reading } from '@element-plus/icons-vue'

defineProps({
  title: {
    type: String,
    default: ''
  }
})

const route = useRoute()
const activeMenu = computed(() => route.path)
</script>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #fff;
  border-bottom: 1px solid var(--el-border-color-light);
  height: 60px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 180px;
}

.logo-icon {
  color: var(--el-color-primary);
}

.title {
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
}

.header-menu {
  border-bottom: none !important;
  flex: 1;
  justify-content: center;
}

.header-menu .el-menu-item {
  border-bottom: none;
}

.header-right {
  min-width: 80px;
  display: flex;
  justify-content: flex-end;
}
</style>
