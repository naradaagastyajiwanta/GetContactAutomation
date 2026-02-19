import { apiClient } from './client'

export async function downloadCsv(): Promise<void> {
  const { data } = await apiClient.get<Blob>('/export/csv', {
    responseType: 'blob',
  })
  const url = URL.createObjectURL(data)
  const link = document.createElement('a')
  link.href = url
  link.download = 'universities-export.csv'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
