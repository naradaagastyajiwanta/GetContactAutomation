import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft,
  Play,
  RefreshCw,
  User,
  GraduationCap,
  Share2,
  Building2,
  Heart,
  Users,
  ExternalLink,
  MapPin,
  Calendar,
  Briefcase,
  BookOpen,
  Instagram,
  Linkedin,
  Facebook,
  Twitter,
  AlertTriangle,
  TrendingUp,
  Newspaper,
  Loader2,
  Mail,
  Phone,
} from 'lucide-react'
import { useCrmRequestDetail, useCrmProfileSources, useRunCrmProfiling } from '../hooks/useCrm'
import type { CrmProfile, CrmProfileSource } from '../api/crm'
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Spinner } from '../components/ui/Spinner'
import { useAuth } from '../context/AuthContext'

function tryParseJson(val: string | null): unknown {
  if (!val) return null
  try {
    return JSON.parse(val)
  } catch {
    return val
  }
}

/** Build a map: display field name → list of source URLs. */
function buildSourceUrlMap(sources: CrmProfileSource[] | undefined): Record<string, string[]> {
  if (!sources) return {}
  const map: Record<string, string[]> = {}
  for (const s of sources) {
    if (s.source_url) {
      const urls = s.source_url.split(', ').filter(Boolean)
      if (urls.length > 0) {
        map[s.field_name] = urls
      }
    }
  }
  return map
}

/** Compact source control that still allows clicking every source URL. */
function SourceLink({ urls }: { urls?: string[] }) {
  if (!urls?.length) return null

  const junkDomains = ['translate.google', 'primevideo.com', 'target.com', 'wa.me', 'accounts.google.com', 'play.google.com']
  const filtered = urls.filter(u => {
    if (!u.startsWith('http')) return false
    if (u.includes('vertexaisearch.cloud.google.com')) return false
    if (junkDomains.some(d => u.includes(d))) return false
    return true
  })
  if (!filtered.length) return null

  const uniqueUrls = [...new Set(filtered)]
  const getDomain = (u: string) => {
    try {
      return new URL(u).hostname.replace('www.', '')
    } catch {
      return u
    }
  }

  return (
    <details className="ml-1 relative inline-block">
      <summary
        title={`Lihat ${uniqueUrls.length} sumber`}
        className="inline-flex cursor-pointer list-none items-center gap-1 rounded px-1 py-0.5 text-indigo-400 hover:text-indigo-600 dark:text-indigo-500 dark:hover:text-indigo-300"
      >
        <ExternalLink className="h-3 w-3" />
        <span className="text-[10px] leading-none">{uniqueUrls.length}</span>
      </summary>
      <div className="absolute right-0 z-20 mt-1 max-h-48 w-72 overflow-auto rounded border border-gray-200 bg-white p-2 shadow-lg dark:border-gray-700 dark:bg-gray-900">
        {uniqueUrls.map((u, i) => (
          <a
            key={i}
            href={u}
            target="_blank"
            rel="noopener noreferrer"
            className="block truncate py-1 text-xs text-indigo-500 hover:text-indigo-700 hover:underline dark:text-indigo-400 dark:hover:text-indigo-300"
            title={u}
          >
            {i + 1}. {getDomain(u)}
          </a>
        ))}
      </div>
    </details>
  )
}

function ConfidenceMeter({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = pct >= 70 ? 'bg-green-500' : pct >= 40 ? 'bg-yellow-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-24 rounded-full bg-gray-200 dark:bg-gray-700">
        <div className={`h-2 rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{pct}%</span>
    </div>
  )
}

function FieldRow({ label, value, icon: Icon, sourceUrls }: { label: string; value: React.ReactNode; icon?: typeof User; sourceUrls?: string[] }) {
  if (!value || value === '—') return null
  return (
    <div className="flex items-start gap-3 py-2">
      {Icon && <Icon className="mt-0.5 h-4 w-4 flex-shrink-0 text-gray-400" />}
      <div>
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
          {label}
          <SourceLink urls={sourceUrls} />
        </p>
        <div className="mt-0.5 text-sm text-gray-900 dark:text-gray-100">{value}</div>
      </div>
    </div>
  )
}

function ListField({ items, sourceUrls }: { items: string[]; sourceUrls?: string[] }) {
  if (!items?.length) return <span className="text-gray-400">—</span>
  return (
    <ul className="space-y-1">
      {items.map((item, i) => (
        <li key={i} className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300">
          <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-indigo-400" />
          {item}
          {i === 0 && <SourceLink urls={sourceUrls} />}
        </li>
      ))}
    </ul>
  )
}

function ProfileSection({
  title,
  icon: Icon,
  children,
}: {
  title: string
  icon: typeof User
  children: React.ReactNode
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Icon className="h-5 w-5 text-indigo-500" />
          <CardTitle>{title}</CardTitle>
        </div>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

function IdentitySection({ profile: p, sourceMap }: { profile: CrmProfile; sourceMap: Record<string, string[]> }) {
  return (
    <ProfileSection title="Identitas" icon={User}>
      <div className="grid gap-x-8 gap-y-1 sm:grid-cols-2">
        <FieldRow label="Nama Lengkap" value={p.full_name} icon={User} sourceUrls={sourceMap['Nama Lengkap']} />
        <FieldRow label="Jabatan" value={p.title} icon={Briefcase} sourceUrls={sourceMap['Jabatan Akademik']} />
        <FieldRow label="Tanggal Lahir" value={p.birth_date} icon={Calendar} sourceUrls={sourceMap['Tanggal Lahir']} />
        <FieldRow label="Usia" value={p.age ? `${p.age} tahun` : null} icon={Calendar} sourceUrls={sourceMap['Usia']} />
        <FieldRow label="Asal Daerah" value={p.origin_region} icon={MapPin} sourceUrls={sourceMap['Asal Daerah']} />
        <FieldRow
          label="Masa Kerja"
          value={p.tenure_years ? `${p.tenure_years} tahun` : null}
          icon={Briefcase}
          sourceUrls={sourceMap['Masa Kerja (tahun)']}
        />
        {p.email && (
          <FieldRow
            label="Email"
            value={
              <a href={`mailto:${p.email}`} className="text-indigo-600 hover:underline dark:text-indigo-400">
                {p.email}
              </a>
            }
            icon={Mail}
            sourceUrls={sourceMap['Email']}
          />
        )}
        {p.phone && (
          <FieldRow
            label="Telepon"
            value={
              <a href={`tel:${p.phone}`} className="text-indigo-600 hover:underline dark:text-indigo-400">
                {p.phone}
              </a>
            }
            icon={Phone}
            sourceUrls={sourceMap['Telepon']}
          />
        )}
      </div>
    </ProfileSection>
  )
}

function AcademicSection({ profile: p, sourceMap }: { profile: CrmProfile; sourceMap: Record<string, string[]> }) {
  const eduHistory = tryParseJson(p.education_history) as Array<Record<string, string>> | null
  const subjects = tryParseJson(p.teaching_subjects) as string[] | null

  return (
    <ProfileSection title="Akademik" icon={GraduationCap}>
      {eduHistory && Array.isArray(eduHistory) && (
        <div className="mb-4">
          <p className="mb-2 text-xs font-medium text-gray-500 dark:text-gray-400">
            Riwayat Pendidikan
            <SourceLink urls={sourceMap['Riwayat Pendidikan']} />
          </p>
          <div className="space-y-2">
            {eduHistory.map((e, i) => (
              <div
                key={i}
                className="flex items-center gap-3 rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-700/50"
              >
                <GraduationCap className="h-4 w-4 text-indigo-400" />
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {e.jenjang} — {e.nama_pt}
                  </p>
                  {e.nama_prodi && (
                    <p className="text-xs text-gray-500 dark:text-gray-400">{e.nama_prodi}</p>
                  )}
                </div>
                {e.tahun_lulus && (
                  <span className="ml-auto text-xs text-gray-400">{e.tahun_lulus}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
      {subjects && subjects.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium text-gray-500 dark:text-gray-400">
            Mata Kuliah
            <SourceLink urls={sourceMap['Mata Kuliah']} />
          </p>
          <div className="flex flex-wrap gap-1.5">
            {subjects.map((s, i) => (
              <Badge key={i} variant="bg-indigo-50 text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-300">
                {s}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </ProfileSection>
  )
}

function SocialSection({ profile: p }: { profile: CrmProfile }) {
  const socials = [
    { label: 'Instagram', value: p.instagram_handle, icon: Instagram, url: p.instagram_handle ? `https://instagram.com/${p.instagram_handle}` : null },
    { label: 'LinkedIn', value: p.linkedin_url, icon: Linkedin, url: p.linkedin_url },
    { label: 'Facebook', value: p.facebook_url, icon: Facebook, url: p.facebook_url },
    { label: 'Twitter/X', value: p.twitter_handle, icon: Twitter, url: p.twitter_handle ? `https://x.com/${p.twitter_handle}` : null },
  ].filter((s) => s.value)

  const otherSocial = tryParseJson(p.other_social) as Record<string, string> | null

  if (!socials.length && !otherSocial) return null

  return (
    <ProfileSection title="Social Media" icon={Share2}>
      <div className="space-y-2">
        {socials.map((s) => (
          <a
            key={s.label}
            href={s.url || '#'}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors hover:bg-gray-50 dark:hover:bg-gray-700/50"
          >
            <s.icon className="h-4 w-4 text-gray-500" />
            <span className="font-medium text-gray-900 dark:text-gray-100">{s.label}</span>
            <span className="text-gray-500 dark:text-gray-400">{s.value}</span>
            <ExternalLink className="ml-auto h-3 w-3 text-gray-400" />
          </a>
        ))}
        {otherSocial &&
          Object.entries(otherSocial).map(([key, val]) => (
            <a
              key={key}
              href={val}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors hover:bg-gray-50 dark:hover:bg-gray-700/50"
            >
              <ExternalLink className="h-4 w-4 text-gray-500" />
              <span className="font-medium capitalize text-gray-900 dark:text-gray-100">{key}</span>
              <span className="truncate text-gray-500 dark:text-gray-400">{val}</span>
            </a>
          ))}
      </div>
    </ProfileSection>
  )
}

function CampusSection({ profile: p, sourceMap }: { profile: CrmProfile; sourceMap: Record<string, string[]> }) {
  const problems = tryParseJson(p.campus_problems) as string[] | null
  const concerns = tryParseJson(p.campus_concerns) as string[] | null
  const hopes = tryParseJson(p.campus_hopes) as string[] | null

  if (!problems?.length && !concerns?.length && !hopes?.length) return null

  return (
    <ProfileSection title="Konteks Kampus" icon={Building2}>
      <div className="grid gap-6 sm:grid-cols-3">
        {problems && problems.length > 0 && (
          <div>
            <div className="mb-2 flex items-center gap-1.5">
              <AlertTriangle className="h-4 w-4 text-red-400" />
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
                Masalah
                <SourceLink urls={sourceMap['Masalah Kampus']} />
              </p>
            </div>
            <ListField items={problems} sourceUrls={sourceMap['Masalah Kampus']} />
          </div>
        )}
        {concerns && concerns.length > 0 && (
          <div>
            <div className="mb-2 flex items-center gap-1.5">
              <TrendingUp className="h-4 w-4 text-yellow-500" />
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
                Kekhawatiran
                <SourceLink urls={sourceMap['Kekhawatiran Kampus']} />
              </p>
            </div>
            <ListField items={concerns} sourceUrls={sourceMap['Kekhawatiran Kampus']} />
          </div>
        )}
        {hopes && hopes.length > 0 && (
          <div>
            <div className="mb-2 flex items-center gap-1.5">
              <TrendingUp className="h-4 w-4 text-green-400" />
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
                Harapan
                <SourceLink urls={sourceMap['Harapan Kampus']} />
              </p>
            </div>
            <ListField items={hopes} sourceUrls={sourceMap['Harapan Kampus']} />
          </div>
        )}
      </div>
    </ProfileSection>
  )
}

function PersonalSection({ profile: p, sourceMap }: { profile: CrmProfile; sourceMap: Record<string, string[]> }) {
  const hobbies = tryParseJson(p.hobbies) as string[] | null
  const activities = tryParseJson(p.outside_activities) as string[] | null

  if (!hobbies?.length && !p.favorite_food && !activities?.length) return null

  return (
    <ProfileSection title="Personal" icon={Heart}>
      <div className="grid gap-x-8 gap-y-1 sm:grid-cols-2">
        {hobbies && hobbies.length > 0 && (
          <div className="py-2">
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
              Hobi
              <SourceLink urls={sourceMap['Hobi']} />
            </p>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {hobbies.map((h, i) => (
                <Badge key={i} variant="bg-pink-50 text-pink-700 dark:bg-pink-900/50 dark:text-pink-300">
                  {h}
                </Badge>
              ))}
            </div>
          </div>
        )}
        <FieldRow label="Makanan Favorit" value={p.favorite_food} sourceUrls={sourceMap['Makanan Favorit']} />
        {activities && activities.length > 0 && (
          <div className="py-2 sm:col-span-2">
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
              Aktivitas Luar Kampus
              <SourceLink urls={sourceMap['Aktivitas Luar Kampus']} />
            </p>
            <div className="mt-1">
              <ListField items={activities} sourceUrls={sourceMap['Aktivitas Luar Kampus']} />
            </div>
          </div>
        )}
      </div>
    </ProfileSection>
  )
}

function FamilySection({ profile: p, sourceMap }: { profile: CrmProfile; sourceMap: Record<string, string[]> }) {
  if (!p.marital_status && !p.spouse_name && p.children_count == null && !p.family_residence) {
    return null
  }

  return (
    <ProfileSection title="Keluarga" icon={Users}>
      <div className="grid gap-x-8 gap-y-1 sm:grid-cols-2">
        <FieldRow
          label="Status"
          value={
            p.marital_status === 'married' ? (
              <Badge variant="bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                Menikah
              </Badge>
            ) : p.marital_status === 'single' ? (
              <Badge variant="bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200">
                Belum Menikah
              </Badge>
            ) : null
          }
          sourceUrls={sourceMap['Status Pernikahan']}
        />
        <FieldRow label="Pasangan" value={p.spouse_name} icon={Heart} sourceUrls={sourceMap['Nama Pasangan']} />
        <FieldRow label="Jumlah Anak" value={p.children_count != null ? String(p.children_count) : null} icon={Users} sourceUrls={sourceMap['Jumlah Anak']} />
        <FieldRow label="Tempat Tinggal" value={p.family_residence} icon={MapPin} sourceUrls={sourceMap['Tempat Tinggal Keluarga']} />
      </div>
    </ProfileSection>
  )
}

function ProcessingState() {
  return (
    <Card className="flex flex-col items-center justify-center py-16">
      <Loader2 className="mb-4 h-12 w-12 animate-spin text-indigo-500" />
      <h3 className="mb-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
        Sedang mengumpulkan data...
      </h3>
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Pipeline OSINT sedang berjalan. Halaman ini akan otomatis refresh.
      </p>
    </Card>
  )
}

export default function CrmDetailPage() {
  const { hasPermission } = useAuth()
  const { id } = useParams<{ id: string }>()
  const requestId = Number(id)
  const { data, isLoading, error } = useCrmRequestDetail(requestId)
  const runMutation = useRunCrmProfiling()
  const canManageCrm = hasPermission('crm.manage')
  const profileId = data?.profile?.id
  const { data: profileData } = useCrmProfileSources(profileId)
  const sourceMap = buildSourceUrlMap(profileData?.sources)

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-4">
        <Link to="/crm" className="inline-flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700">
          <ArrowLeft className="h-4 w-4" /> Kembali
        </Link>
        <Card className="border-red-200 dark:border-red-800">
          <CardContent className="py-8 text-center">
            <AlertTriangle className="mx-auto mb-3 h-10 w-10 text-red-500" />
            <p className="text-red-700 dark:text-red-300">Gagal memuat data: {(error as Error).message}</p>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (!data?.request) {
    return (
      <div className="space-y-4">
        <Link to="/crm" className="inline-flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700">
          <ArrowLeft className="h-4 w-4" /> Kembali
        </Link>
        <Card>
          <CardContent className="py-8 text-center">
            <p className="text-gray-500">Request tidak ditemukan</p>
          </CardContent>
        </Card>
      </div>
    )
  }

  const { request, profile } = data

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link
            to="/crm"
            className="rounded-lg p-2 text-gray-500 transition-colors hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <ArrowLeft className="h-5 w-5" />
          </Link>
          {profile?.photo_url ? (
            <img
              src={profile.photo_url}
              alt={request.pic_name}
              className="h-14 w-14 rounded-full object-cover ring-2 ring-gray-200 dark:ring-gray-700"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
          ) : (
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-indigo-100 text-indigo-600 dark:bg-indigo-900/50 dark:text-indigo-400">
              <User className="h-7 w-7" />
            </div>
          )}
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{request.pic_name}</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {request.university_name || '—'} {request.pic_title && `• ${request.pic_title}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {profile && (
            <div className="text-right">
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {profile.fields_found}/{profile.fields_total} fields
              </p>
              <ConfidenceMeter value={profile.overall_confidence || 0} />
            </div>
          )}
          {canManageCrm && (request.status === 'pending' || request.status === 'failed') && (
            <Button
              onClick={() => runMutation.mutate(requestId)}
              loading={runMutation.isPending}
            >
              <Play className="h-4 w-4" />
              {request.status === 'failed' ? 'Retry' : 'Run'}
            </Button>
          )}
          {canManageCrm && request.status === 'completed' && (
            <Button
              variant="outline"
              onClick={() => {
                if (window.confirm('Re-research akan menjalankan ulang seluruh pipeline OSINT. Lanjutkan?')) {
                  runMutation.mutate(requestId)
                }
              }}
              loading={runMutation.isPending}
            >
              <RefreshCw className="h-4 w-4" />
              Re-research
            </Button>
          )}
        </div>
      </div>

      {/* Processing state */}
      {request.status === 'processing' && <ProcessingState />}

      {/* Profile sections */}
      {profile && (
        <div className="space-y-6">
          <IdentitySection profile={profile} sourceMap={sourceMap} />
          <AcademicSection profile={profile} sourceMap={sourceMap} />
          <SocialSection profile={profile} />
          <CampusSection profile={profile} sourceMap={sourceMap} />
          <PersonalSection profile={profile} sourceMap={sourceMap} />
          <FamilySection profile={profile} sourceMap={sourceMap} />

          {/* Recent news */}
          {(() => {
            const news = tryParseJson(profile.campus_hopes)
            // Check for recent_news from campus context — not stored separately,
            // it's embedded in the compiled profile or we can show campus_hopes
            return null
          })()}
        </div>
      )}

      {/* Pending state — no profile yet */}
      {!profile && request.status === 'pending' && (
        <Card className="flex flex-col items-center justify-center py-16">
          <BookOpen className="mb-4 h-12 w-12 text-gray-400 dark:text-gray-500" />
          <h3 className="mb-1 text-lg font-medium text-gray-900 dark:text-gray-100">
            Belum ada profil
          </h3>
          <p className="mb-4 text-sm text-gray-500 dark:text-gray-400">
            Klik &quot;Run&quot; untuk mulai mengumpulkan data OSINT
          </p>
          {canManageCrm && (
            <Button onClick={() => runMutation.mutate(requestId)} loading={runMutation.isPending}>
              <Play className="h-4 w-4" />
              Jalankan Profiling
            </Button>
          )}
        </Card>
      )}
    </div>
  )
}
