export const KIND_LABELS = {
  photo: 'Photo',
  video: 'Video',
  floorplan: 'Floor plan',
  sensor: 'Sensor log',
}

export const STATUS_LABELS = {
  uploading: 'Uploading',
  stored: 'Stored',
  ready: 'Ready',
  failed: 'Failed',
}

export const STATUS_TONE = {
  uploading: 'warning',
  stored: 'accent',
  ready: 'success',
  failed: 'danger',
}

export const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'photo', label: 'Photos' },
  { key: 'video', label: 'Videos' },
  { key: 'floorplan', label: 'Floor plans' },
  { key: 'sensor', label: 'Sensor logs' },
]

export const kindLabel = (kind) => KIND_LABELS[kind] || kind || 'File'
export const statusLabel = (status) => STATUS_LABELS[status] || status || 'Unknown'
