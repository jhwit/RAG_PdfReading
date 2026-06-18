/**
 * 格式化工具函数
 */

/**
 * 格式化 ISO 日期字符串为中文格式
 * @param {string} isoString - ISO 8601 日期字符串
 * @returns {string} 格式化后的日期
 */
export function formatDate(isoString) {
  if (!isoString) return '-'
  const date = new Date(isoString)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}`
}

/**
 * 格式化文件大小
 * @param {number} bytes - 字节数
 * @returns {string}
 */
export function formatFileSize(bytes) {
  if (!bytes || bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const k = 1024
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + units[i]
}

/**
 * 文档状态映射
 */
const STATUS_MAP = {
  pending: { label: '待处理', type: 'info' },
  processing: { label: '处理中', type: 'warning' },
  completed: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' }
}

/**
 * 获取状态中文标签
 * @param {string} status
 * @returns {string}
 */
export function statusLabel(status) {
  return STATUS_MAP[status]?.label || status || '-'
}

/**
 * 获取状态对应的 Element Plus Tag 类型
 * @param {string} status
 * @returns {string}
 */
export function statusType(status) {
  return STATUS_MAP[status]?.type || 'info'
}

/**
 * 截断文本
 * @param {string} text
 * @param {number} maxLength
 * @returns {string}
 */
export function truncateText(text, maxLength = 100) {
  if (!text || text.length <= maxLength) return text || ''
  return text.slice(0, maxLength) + '...'
}
