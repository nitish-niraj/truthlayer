export function short(text = '', max = 120) {
  if (text.length <= max) return text
  return text.slice(0, max - 1) + '…'
}

export function formatBytes(bytes) {
  if (!bytes || bytes < 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let i = 0
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024
    i++
  }
  const decimals = value < 10 && i > 0 ? 1 : 0
  return `${value.toFixed(decimals)} ${units[i]}`
}
