import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import axios from 'axios'
import { Database, LockKeyhole, ShieldCheck } from 'lucide-react'
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
              Login memakai akun DMS karyawan aktif
            </div>
            <h1 className="max-w-2xl text-4xl font-semibold tracking-tight text-white md:text-5xl">
              DMS Marketing Dashboard Access
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300 md:text-lg">
              Dashboard ini memakai identitas user dari DMS `karyawan`, hanya untuk akun dengan `statuskerja = 1`,
              lalu otorisasi dashboard dikelola secara lokal di aplikasi ini.
            </p>

            <div className="mt-8 grid gap-4 md:grid-cols-2">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur">
                <ShieldCheck className="mb-3 h-5 w-5 text-emerald-300" />
                <p className="text-sm font-medium text-white">Session berbasis cookie HTTP-only</p>
                <p className="mt-2 text-sm leading-6 text-slate-300">
                  Kredensial divalidasi ke DMS, lalu browser memakai session lokal yang lebih aman untuk dashboard web.
                </p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur">
                <LockKeyhole className="mb-3 h-5 w-5 text-sky-300" />
                <p className="text-sm font-medium text-white">Role mapping lokal</p>
                <p className="mt-2 text-sm leading-6 text-slate-300">
                  Role dashboard tidak diambil langsung dari DMS. Akses diatur lokal agar permission bisa dikendalikan penuh.
                </p>
              </div>
            </div>
          </div>

          <Card className="border-white/10 bg-white/95 p-8 text-slate-900 shadow-2xl shadow-black/30 dark:bg-slate-900 dark:text-white">
            <div className="mb-6">
              <p className="text-sm font-medium uppercase tracking-[0.18em] text-indigo-600 dark:text-indigo-300">
                {bootstrapRequired ? 'Initial Setup' : 'User Login'}
              </p>
              <h2 className="mt-2 text-2xl font-semibold">
                {bootstrapRequired ? 'Claim admin access' : 'Sign in to continue'}
              </h2>
              <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">
                {bootstrapRequired
                  ? 'Belum ada role lokal yang terpasang. Akun DMS pertama yang valid akan dijadikan admin dashboard.'
                  : 'Masukkan email dan password DMS Anda untuk membuka dashboard.'}
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
                  placeholder="nama@company.com"
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
                  placeholder="Password DMS"
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
                {bootstrapRequired ? 'Claim Admin Access' : 'Login'}
              </Button>
            </form>
          </Card>
        </div>
      </div>
    </div>
  )
}