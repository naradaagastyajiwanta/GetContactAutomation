import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import axios from 'axios'
import { Database, GitBranch, Megaphone } from 'lucide-react'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { getBootstrapStatus, login, setupInitialAdmin } from '../api/auth'
import { queryKeys } from '../lib/queryKeys'
import { useAuth } from '../context/AuthContext'

const BOOTSTRAP_COMPLETED_MESSAGE = 'Auth bootstrap has already been completed'

function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    return error.response?.data?.detail || error.message
  }
  if (error instanceof Error) return error.message
  return 'Unknown error'
}

export default function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const { isAuthenticated, isLoading } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [bootstrapOverride, setBootstrapOverride] = useState<boolean | null>(null)

  const bootstrapQuery = useQuery({
    queryKey: queryKeys.auth.bootstrap,
    queryFn: getBootstrapStatus,
    retry: false,
  })

  const bootstrapRequired = bootstrapOverride ?? bootstrapQuery.data?.required ?? false
  const redirectTo = useMemo(() => {
    const state = location.state as { from?: { pathname?: string } } | null
    return state?.from?.pathname || '/'
  }, [location.state])

  const authMutation = useMutation({
    mutationFn: async () => {
      const liveBootstrapStatus = await getBootstrapStatus()
      setBootstrapOverride(liveBootstrapStatus.required)

      if (liveBootstrapStatus.required) {
        try {
          return await setupInitialAdmin({ email, password, role_key: 'admin' })
        } catch (error) {
          if (axios.isAxiosError(error) && error.response?.status === 409) {
            const detail = error.response?.data?.detail
            if (detail === BOOTSTRAP_COMPLETED_MESSAGE) {
              setBootstrapOverride(false)
              await queryClient.invalidateQueries({ queryKey: queryKeys.auth.bootstrap })
              return login({ email, password })
            }
          }
          throw error
        }
      }

      return login({ email, password })
    },
    onSuccess: async () => {
      setBootstrapOverride(false)
      await queryClient.invalidateQueries({ queryKey: queryKeys.auth.bootstrap })
      await queryClient.invalidateQueries({ queryKey: queryKeys.auth.me })
      navigate(redirectTo, { replace: true })
    },
  })

  if (!isLoading && isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-slate-950 text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(99,102,241,0.22),_transparent_32%),radial-gradient(circle_at_bottom_right,_rgba(16,185,129,0.18),_transparent_28%)]" />
      <div className="absolute inset-0 opacity-20 [background-image:linear-gradient(rgba(255,255,255,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.08)_1px,transparent_1px)] [background-size:36px_36px]" />

      <div className="relative mx-auto flex min-h-screen max-w-6xl items-center px-6 py-12">
        <div className="grid w-full gap-10 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="flex flex-col justify-center">
            <div className="mb-6 inline-flex w-fit items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 py-2 text-sm text-slate-200 backdrop-blur">
              <Database className="h-4 w-4" />
              DMS Marketing Dashboard
            </div>
            <h1 className="max-w-2xl text-4xl font-semibold tracking-tight text-white md:text-5xl">
              Satu dashboard untuk operasional DMS Marketing
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300 md:text-lg">
              DMS Marketing dipakai untuk memantau pipeline kampus, mengelola percakapan dan audiensi,
              menjalankan blast WhatsApp atau email, serta melihat profiling PIC dalam satu workspace.
            </p>

            <div className="mt-8 grid gap-4 md:grid-cols-2">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur">
                <GitBranch className="mb-3 h-5 w-5 text-emerald-300" />
                <p className="text-sm font-medium text-white">Pantau pipeline dan outreach</p>
                <p className="mt-2 text-sm leading-6 text-slate-300">
                  Akses data universitas, group target, conversation, audiensi, dan progress pipeline dari satu tempat.
                </p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur">
                <Megaphone className="mb-3 h-5 w-5 text-sky-300" />
                <p className="text-sm font-medium text-white">Kelola blast dan insight</p>
                <p className="mt-2 text-sm leading-6 text-slate-300">
                  Jalankan WhatsApp, WA Blast, Email Blast, Knowledge Base, sampai PIC Profiling sesuai role yang Anda miliki.
                </p>
              </div>
            </div>
          </div>

          <Card className="border-white/10 bg-white/95 p-8 text-slate-900 shadow-2xl shadow-black/30 dark:bg-slate-900 dark:text-white">
            <div className="mb-6">
              <p className="text-sm font-medium uppercase tracking-[0.18em] text-indigo-600 dark:text-indigo-300">
                {bootstrapRequired ? 'Setup Awal' : 'Masuk Dashboard'}
              </p>
              <h2 className="mt-2 text-2xl font-semibold">
                {bootstrapRequired ? 'Aktifkan admin pertama' : 'Selamat datang kembali'}
              </h2>
              <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">
                {bootstrapRequired
                  ? 'Belum ada akun dashboard yang aktif. Masuk dengan akun DMS yang valid untuk mengambil akses admin pertama.'
                  : 'Masuk dengan akun DMS aktif untuk membuka dashboard dan fitur yang sesuai dengan peran Anda.'}
              </p>
            </div>

            <form
              className="space-y-5"
              onSubmit={(event) => {
                event.preventDefault()
                authMutation.mutate()
              }}
            >
              <div>
                <label className="mb-2 block text-sm font-medium">Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 dark:border-slate-700 dark:bg-slate-800"
                  placeholder="nama@domain.com"
                  autoComplete="username"
                  required
                />
              </div>

              <div>
                <label className="mb-2 block text-sm font-medium">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 dark:border-slate-700 dark:bg-slate-800"
                  placeholder="Masukkan password Anda"
                  autoComplete="current-password"
                  required
                />
              </div>

              {authMutation.isError && (
                <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200">
                  {getErrorMessage(authMutation.error)}
                </div>
              )}

              <Button type="submit" className="w-full justify-center" size="lg" loading={authMutation.isPending || bootstrapQuery.isLoading}>
                {bootstrapRequired ? 'Aktifkan Akses Admin' : 'Masuk'}
              </Button>

              <p className="text-center text-xs leading-5 text-slate-500 dark:text-slate-400">
                {bootstrapRequired
                  ? 'Akun valid pertama akan langsung menjadi admin aplikasi ini.'
                  : 'Jika akun Anda belum punya akses, hubungi admin dashboard untuk aktivasi peran.'}
              </p>
            </form>
          </Card>
        </div>
      </div>
    </div>
  )
}