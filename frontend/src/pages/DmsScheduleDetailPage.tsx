import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import {
  ArrowLeft,
  CalendarDays,
  Clock,
  Video,
  MapPin,
  Users,
  FileText,
  ExternalLink,
  Mail,
  Phone,
  Link2,
  Building2,
} from 'lucide-react'
import { useDmsScheduleDetail, useDmsFollowupsByUniversity } from '../hooks/useDms'
import { DmsFollowupTimeline } from '../components/dms/DmsFollowupTimeline'
import { DmsResearchCard } from '../components/dms/DmsResearchCard'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/Card'
import { Spinner } from '../components/ui/Spinner'

function formatDateLong(dateStr: string | null): string {
  if (!dateStr) return '-'
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString('id-ID', {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    })
  } catch {
    return dateStr
  }
}

const APPROVAL_COLORS: Record<string, { bg: string; text: string }> = {
  Approved: {
    bg: 'bg-green-100 dark:bg-green-900/50',
    text: 'text-green-700 dark:text-green-300',
  },
  'Waiting for Approval': {
    bg: 'bg-yellow-100 dark:bg-yellow-900/50',
    text: 'text-yellow-700 dark:text-yellow-300',
  },
  Rejected: {
    bg: 'bg-red-100 dark:bg-red-900/50',
    text: 'text-red-700 dark:text-red-300',
  },
  diterima: {
    bg: 'bg-green-100 dark:bg-green-900/50',
    text: 'text-green-700 dark:text-green-300',
  },
  request: {
    bg: 'bg-blue-100 dark:bg-blue-900/50',
    text: 'text-blue-700 dark:text-blue-300',
  },
  pembuatan: {
    bg: 'bg-yellow-100 dark:bg-yellow-900/50',
    text: 'text-yellow-700 dark:text-yellow-300',
  },
  pengiriman: {
    bg: 'bg-purple-100 dark:bg-purple-900/50',
    text: 'text-purple-700 dark:text-purple-300',
  },
  akan_datang: {
    bg: 'bg-blue-100 dark:bg-blue-900/50',
    text: 'text-blue-700 dark:text-blue-300',
  },
  sedang_berjalan: {
    bg: 'bg-amber-100 dark:bg-amber-900/50',
    text: 'text-amber-700 dark:text-amber-300',
  },
  selesai: {
    bg: 'bg-green-100 dark:bg-green-900/50',
    text: 'text-green-700 dark:text-green-300',
  },
  terlambat: {
    bg: 'bg-red-100 dark:bg-red-900/50',
    text: 'text-red-700 dark:text-red-300',
  },
}

export default function DmsScheduleDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const scheduleId = Number(id) || 0
  const source = searchParams.get('source') || 'schedule_follow_up'

  const { data: schedule, isLoading } = useDmsScheduleDetail(scheduleId, source)
  const { data: followupsData } = useDmsFollowupsByUniversity(schedule?.id_univ ?? 0, 30)

  const isLsp = source === 'schedule_follow_up_lsp'

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner size="lg" />
      </div>
    )
  }

  if (!schedule) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate('/dms-schedules')}>
          <ArrowLeft className="h-4 w-4" />
          Back to Schedules
        </Button>
        <p className="text-center text-gray-500 dark:text-gray-400">Schedule not found.</p>
      </div>
    )
  }

  const approvalStyle = APPROVAL_COLORS[schedule.status_approval ?? ''] ?? {
    bg: 'bg-gray-100 dark:bg-gray-700',
    text: 'text-gray-600 dark:text-gray-400',
  }

  const docLinks = [
    { label: 'Company Profile', url: schedule.company_profile_link },
    { label: 'Proposal', url: schedule.proposal_link },
    { label: 'Surat Penawaran', url: schedule.surat_penawaran_link },
    { label: 'MoU', url: schedule.mou_link },
    { label: 'PKS', url: schedule.pks_link },
  ].filter((d) => d.url)

  const followups = followupsData?.followups ?? []

  return (
    <div className="space-y-6">
      {/* Back button */}
      <Button variant="ghost" onClick={() => navigate('/dms-schedules')}>
        <ArrowLeft className="h-4 w-4" />
        Back to Schedules
      </Button>

      {/* Header Card */}
      <Card>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
                {schedule.nama_universitas ?? `University #${schedule.id_univ}`}
              </h1>
              {isLsp && (
                <Badge className="bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300">
                  LSP Audiensi
                </Badge>
              )}
            </div>

            {isLsp && schedule.meeting_topic && (
              <p className="text-sm text-emerald-600 dark:text-emerald-400 font-medium">
                {schedule.meeting_topic}
                {schedule.meeting_lembaga && (
                  <span className="ml-2 text-gray-500 dark:text-gray-400">({schedule.meeting_lembaga})</span>
                )}
              </p>
            )}

            <div className="flex flex-wrap items-center gap-3 text-sm text-gray-600 dark:text-gray-300">
              <span className="inline-flex items-center gap-1">
                <CalendarDays className="h-4 w-4 text-gray-400" />
                {formatDateLong(schedule.jadwal_audiensi)}
              </span>
              {schedule.jam_audensi && (
                <span className="inline-flex items-center gap-1">
                  <Clock className="h-4 w-4 text-gray-400" />
                  {schedule.jam_audensi}
                </span>
              )}
              {schedule.type_meeting && (
                <span className="inline-flex items-center gap-1">
                  {schedule.type_meeting?.toLowerCase().includes('zoom') ? (
                    <Video className="h-4 w-4 text-blue-500" />
                  ) : (
                    <MapPin className="h-4 w-4 text-orange-500" />
                  )}
                  {schedule.type_meeting}
                </span>
              )}
            </div>

            {schedule.alamat_universitas && (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                <MapPin className="mr-1 inline h-3.5 w-3.5" />
                {schedule.alamat_universitas}
              </p>
            )}
            {schedule.email_kampus && (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                <Mail className="mr-1 inline h-3.5 w-3.5" />
                {schedule.email_kampus}
              </p>
            )}
          </div>

          <div className="flex flex-col items-end gap-2">
            {schedule.status_approval && (
              <Badge className={`${approvalStyle.bg} ${approvalStyle.text} text-sm px-3 py-1`}>
                {schedule.status_approval}
              </Badge>
            )}
            {schedule.est_audiens != null && (
              <span className="text-xs text-gray-500 dark:text-gray-400">
                Est. {schedule.est_audiens} audiens
                {schedule.aktual_audiens != null && ` / Aktual ${schedule.aktual_audiens}`}
              </span>
            )}
            {isLsp && schedule.meeting_status && (() => {
              const ms = APPROVAL_COLORS[schedule.meeting_status] ?? {
                bg: 'bg-gray-100 dark:bg-gray-700',
                text: 'text-gray-600 dark:text-gray-400',
              }
              return (
                <Badge className={`${ms.bg} ${ms.text} text-sm px-3 py-1`}>
                  {schedule.meeting_status.replace(/_/g, ' ')}
                </Badge>
              )
            })()}
          </div>
        </div>
      </Card>

      {/* Two-column grid */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* LSP Schedule Info (only for LSP source) */}
        {isLsp && (
          <Card>
            <CardHeader>
              <CardTitle>
                <Building2 className="mr-2 inline h-5 w-5 text-emerald-500" />
                LSP Schedule Info
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {schedule.tanggal_schedule && (
                <div>
                  <p className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">Tanggal Schedule</p>
                  <p className="text-sm text-gray-900 dark:text-gray-100">{formatDateLong(schedule.tanggal_schedule)}</p>
                </div>
              )}
              {schedule.tanggal_meeting && (
                <div>
                  <p className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">Tanggal Meeting</p>
                  <p className="text-sm text-gray-900 dark:text-gray-100">{formatDateLong(schedule.tanggal_meeting)}</p>
                </div>
              )}
              {schedule.namapimpinan && (
                <div>
                  <p className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">Pimpinan</p>
                  <p className="text-sm text-gray-900 dark:text-gray-100">
                    {schedule.namapimpinan}
                    {schedule.jabatanpic && <span className="ml-1 text-gray-500">({schedule.jabatanpic})</span>}
                  </p>
                </div>
              )}
              {schedule.skema && (
                <div>
                  <p className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">Skema</p>
                  <p className="text-sm text-gray-900 dark:text-gray-100">{schedule.skema}</p>
                </div>
              )}
              {(schedule.expired_mou || schedule.expired_moa) && (
                <div className="flex gap-4">
                  {schedule.expired_mou && (
                    <div>
                      <p className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">Expired MoU</p>
                      <p className="text-sm text-gray-900 dark:text-gray-100">{formatDateLong(schedule.expired_mou)}</p>
                    </div>
                  )}
                  {schedule.expired_moa && (
                    <div>
                      <p className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">Expired MoA</p>
                      <p className="text-sm text-gray-900 dark:text-gray-100">{formatDateLong(schedule.expired_moa)}</p>
                    </div>
                  )}
                </div>
              )}
              {schedule.passcode && (
                <div>
                  <p className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">Passcode</p>
                  <p className="text-sm font-mono text-gray-900 dark:text-gray-100">{schedule.passcode}</p>
                </div>
              )}
              {schedule.lokasi && (
                <div>
                  <p className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">Lokasi</p>
                  <p className="text-sm text-gray-900 dark:text-gray-100">{schedule.lokasi}</p>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Meeting Info */}
        <Card>
          <CardHeader>
            <CardTitle>
              <Video className="mr-2 inline h-5 w-5 text-blue-500" />
              Meeting Info
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {schedule.link_zoom ? (
              <div>
                <p className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">
                  Zoom Link
                </p>
                <a
                  href={schedule.link_zoom}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline dark:text-blue-400"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  {schedule.link_zoom.length > 60
                    ? schedule.link_zoom.slice(0, 60) + '...'
                    : schedule.link_zoom}
                </a>
              </div>
            ) : (
              <p className="text-sm text-gray-500 dark:text-gray-400">No Zoom link provided.</p>
            )}

            {schedule.meetings && schedule.meetings.length > 0 && (
              <div className="space-y-2">
                {schedule.meetings.map((m) => (
                  <div
                    key={m.id}
                    className="rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-800/50"
                  >
                    {m.topic && (
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {m.topic}
                      </p>
                    )}
                    {m.passcode && (
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        Passcode: <span className="font-mono">{m.passcode}</span>
                      </p>
                    )}
                    {m.duration_minutes && (
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        Duration: {m.duration_minutes} min
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}

            {schedule.jenis_meetings && (
              <div>
                <p className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">
                  Jenis Meeting
                </p>
                <p className="text-sm text-gray-900 dark:text-gray-100">{schedule.jenis_meetings}</p>
              </div>
            )}

            {schedule.alamat && (
              <div>
                <p className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">
                  Alamat Meeting
                </p>
                <p className="text-sm text-gray-900 dark:text-gray-100">{schedule.alamat}</p>
                {schedule.link_lokasi && (
                  <a
                    href={schedule.link_lokasi}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 inline-flex items-center gap-1 text-xs text-blue-600 hover:underline dark:text-blue-400"
                  >
                    <Link2 className="h-3 w-3" />
                    Open in Maps
                  </a>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* PIC Contacts */}
        <Card>
          <CardHeader>
            <CardTitle>
              <Users className="mr-2 inline h-5 w-5 text-amber-500" />
              PIC Contacts
            </CardTitle>
          </CardHeader>
          <CardContent>
            {schedule.pics && schedule.pics.length > 0 ? (
              <div className="space-y-3">
                {schedule.pics.map((pic, idx) => (
                  <div
                    key={idx}
                    className="rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-800/50"
                  >
                    <p className="font-medium text-gray-900 dark:text-gray-100">
                      {pic.nama_pic ?? 'Unknown'}
                    </p>
                    {pic.jabatan_pic && (
                      <p className="text-xs text-gray-500 dark:text-gray-400">{pic.jabatan_pic}</p>
                    )}
                    {pic.no_pic && (
                      <p className="mt-1 inline-flex items-center gap-1 text-sm text-green-600 dark:text-green-400">
                        <Phone className="h-3.5 w-3.5" />
                        {pic.no_pic}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-500 dark:text-gray-400">No PIC data available.</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Documents */}
      {docLinks.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>
              <FileText className="mr-2 inline h-5 w-5 text-gray-500" />
              Documents
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {docLinks.map((doc) => (
                <a
                  key={doc.label}
                  href={doc.url!}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  {doc.label}
                </a>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Notes */}
      {(schedule.catatan || schedule.catatan_marketing || schedule.notulen) && (
        <Card>
          <CardHeader>
            <CardTitle>Notes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {schedule.catatan && (
              <div>
                <p className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">
                  Catatan
                </p>
                <p className="text-sm text-gray-900 dark:text-gray-100 whitespace-pre-wrap">{schedule.catatan}</p>
              </div>
            )}
            {schedule.catatan_marketing && (
              <div>
                <p className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">
                  Catatan Marketing
                </p>
                <p className="text-sm text-gray-900 dark:text-gray-100 whitespace-pre-wrap">
                  {schedule.catatan_marketing}
                </p>
              </div>
            )}
            {schedule.notulen && (
              <div>
                <p className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">
                  Notulen
                </p>
                <p className="text-sm text-gray-900 dark:text-gray-100 whitespace-pre-wrap">{schedule.notulen}</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Research Card */}
      <DmsResearchCard
        scheduleId={scheduleId}
        source={source}
        universityName={schedule.nama_universitas ?? undefined}
      />

      {/* Follow-up History */}
      <Card>
        <CardHeader>
          <CardTitle>
            Follow-up History ({followups.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          <DmsFollowupTimeline followups={followups} />
        </CardContent>
      </Card>
    </div>
  )
}
