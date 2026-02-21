export const queryKeys = {
  dashboard: ['dashboard'] as const,
  health: ['health'] as const,
  control: ['control'] as const,
  pipeline: {
    status: ['pipeline', 'status'] as const,
  },
  universities: {
    all: ['universities'] as const,
    list: (params: Record<string, unknown>) => ['universities', 'list', params] as const,
    detail: (id: number) => ['universities', 'detail', id] as const,
    contacts: (id: number) => ['universities', 'contacts', id] as const,
    posts: (id: number) => ['universities', 'posts', id] as const,
  },
  conversations: {
    all: ['conversations'] as const,
    list: (params: Record<string, unknown>) => ['conversations', 'list', params] as const,
    detail: (id: number) => ['conversations', 'detail', id] as const,
  },
  learning: {
    all: ['learning'] as const,
    lessons: ['learning', 'lessons'] as const,
    analyses: ['learning', 'analyses'] as const,
    stats: ['learning', 'stats'] as const,
  },
  whatsapp: {
    all: ['whatsapp'] as const,
    qr: ['whatsapp', 'qr'] as const,
    status: ['whatsapp', 'status'] as const,
  },
  audiensi: {
    all: ['audiensi'] as const,
    list: (params: Record<string, unknown>) => ['audiensi', 'list', params] as const,
    detail: (id: number) => ['audiensi', 'detail', id] as const,
    queue: ['audiensi', 'queue'] as const,
    stats: ['audiensi', 'stats'] as const,
  },
  knowledge: {
    all: ['knowledge'] as const,
    list: (type?: string) => ['knowledge', 'list', type] as const,
  },
  apiLogs: {
    all: ['api-logs'] as const,
    list: (params: Record<string, unknown>) => ['api-logs', 'list', params] as const,
    detail: (id: number) => ['api-logs', 'detail', id] as const,
  },
  config: ['config'] as const,
  models: ['config', 'models'] as const,
}
