import axios from 'axios'

export const apiClient = axios.create({
  baseURL: '/api',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status
    const requestUrl = typeof error?.config?.url === 'string' ? error.config.url : ''
    const isAuthMeRequest = requestUrl.endsWith('/auth/me')

    if (status === 401 && !isAuthMeRequest && typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('app:unauthorized'))
    }
    return Promise.reject(error)
  },
)
