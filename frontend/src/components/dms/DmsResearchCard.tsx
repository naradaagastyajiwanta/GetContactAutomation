import { useEffect, useRef, useState } from 'react'
import { GraduationCap, ExternalLink, RefreshCw, Search, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/Card'
import { Button } from '../ui/Button'
import { useDmsResearchBySchedule, useTriggerResearch } from '../../hooks/useDms'
import type { DmsResearchData } from '../../api/dms'

interface DmsResearchCardProps {
  scheduleId: number
  source: string
  universityName?: string
}

function SourceChip({ url }: { url?: string | null }) {
  if (!url || !url.startsWith('http')) return null
  let display = url.replace(/^https?:\/\//, '').replace(/\/$/, '')
  if (display.length > 40) display = display.slice(0, 40) + '\u2026'
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="mt-2 inline-flex items-center gap-1 rounded border border-blue-200 bg-blue-50 px-2 py-0.5 text-xs text-blue-600 hover:bg-blue-100 transition-colors dark:border-blue-800/60 dark:bg-blue-950/30 dark:text-blue-400 dark:hover:bg-blue-950/60"
    >
      <ExternalLink className="h-3 w-3 flex-shrink-0" />
      <span>{display}</span>
    </a>
  )
}

function InfoBlock({
  emoji,
  label,
  content,
  sourceUrl,
}: {
  emoji: string
  label: string
  content: string
  sourceUrl?: string | null
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-800/50">
      <p className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">
        {emoji} {label}
      </p>
      <p className="text-sm text-gray-800 dark:text-gray-200 leading-relaxed">{content}</p>
      <SourceChip url={sourceUrl} />
    </div>
  )
}

function ResearchingOverlay() {
  const steps = [
    'Mencari profil rektor aktif\u2026',
    'Mengidentifikasi kota kelahiran\u2026',
    'Mencari destinasi wisata\u2026',
    'Mencari makanan khas\u2026',
    'Menganalisis psikografis rektor\u2026',
    'Mengumpulkan sumber referensi\u2026',
    'Memfinalisasi hasil riset\u2026',
  ]
  const [step, setStep] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setStep((s) => (s + 1) % steps.length), 2500)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="flex flex-col items-center justify-center gap-4 py-14 text-center">
      <div className="relative">
        <div className="h-16 w-16 rounded-full border-4 border-indigo-100 dark:border-indigo-900/40" />
        <div className="absolute inset-0 h-16 w-16 animate-spin rounded-full border-4 border-transparent border-t-indigo-500" />
        <GraduationCap className="absolute inset-0 m-auto h-7 w-7 text-indigo-500" />
      </div>
      <div>
        <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">
          AI sedang melakukan riset…
        </p>
        <p className="mt-1 text-xs text-indigo-500 dark:text-indigo-400 animate-pulse">
          {steps[step]}
        </p>
      </div>
      <p className="max-w-xs text-xs text-gray-400 dark:text-gray-500">
        Proses ini membutuhkan 15–30 detik. Hasilnya akan muncul otomatis.
      </p>
    </div>
  )
}

function ResearchBody({
  rd,
  research,
}: {
  rd: DmsResearchData
  research: { university_name: string | null; university_city: string | null; researched_at: string | null }
}) {
  return (
    <div className="space-y-5">
      {/* Rector hero */}
      <div className="rounded-xl border border-indigo-200 bg-indigo-50 px-5 py-4 dark:border-indigo-800/60 dark:bg-indigo-950/30">
        <p className="text-lg font-bold text-indigo-900 dark:text-indigo-200">
          {rd.rector_name ?? '\u2014'}
        </p>
        <p className="mt-0.5 text-sm text-indigo-600 dark:text-indigo-400">
          Rektor {research.university_name ?? ''}
          {(rd.rector_birth_year || rd.rector_birth_city) && (
            <span className="ml-2 text-indigo-400 dark:text-indigo-500">
              {'\u00B7'} Lahir{rd.rector_birth_year ? ` ${rd.rector_birth_year}` : ''}
              {rd.rector_birth_city ? ` di ${rd.rector_birth_city}` : ''}
            </span>
          )}
        </p>
        <SourceChip url={rd.rector_source} />
      </div>

      {/* Info grid */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {rd.tourism_rector_birth_youth && (
          <InfoBlock
            emoji={'\uD83D\uDDFA\uFE0F'}
            label={`Wisata Kota Lahir \u2014 remaja${rd.rector_birth_city ? ` (${rd.rector_birth_city})` : ''}`}
            content={rd.tourism_rector_birth_youth}
            sourceUrl={rd.tourism_rector_birth_youth_source}
          />
        )}
        {rd.tourism_rector_birth_current && (
          <InfoBlock
            emoji={'\uD83C\uDFD9\uFE0F'}
            label={`Wisata Kota Lahir \u2014 kini${rd.rector_birth_city ? ` (${rd.rector_birth_city})` : ''}`}
            content={rd.tourism_rector_birth_current}
            sourceUrl={rd.tourism_rector_birth_current_source}
          />
        )}
        {rd.tourism_university_city && (
          <InfoBlock
            emoji={'\uD83C\uDFDB\uFE0F'}
            label={`Wisata Kota Kampus${research.university_city ? ` (${research.university_city})` : ''}`}
            content={rd.tourism_university_city}
            sourceUrl={rd.tourism_university_city_source}
          />
        )}
        {rd.food_rector_birth_city && (
          <InfoBlock
            emoji={'\uD83C\uDF5C'}
            label={`Makanan Khas Kota Lahir${rd.rector_birth_city ? ` (${rd.rector_birth_city})` : ''}`}
            content={rd.food_rector_birth_city}
            sourceUrl={rd.food_rector_birth_city_source}
          />
        )}
        {rd.food_university_city && (
          <InfoBlock
            emoji={'\uD83C\uDF7D\uFE0F'}
            label={`Makanan Khas Kota Kampus${research.university_city ? ` (${research.university_city})` : ''}`}
            content={rd.food_university_city}
            sourceUrl={rd.food_university_city_source}
          />
        )}
      </div>

      {/* Psychographics */}
      {rd.psychographics && (
        <div className="rounded-xl border border-purple-200 bg-purple-50 px-5 py-4 dark:border-purple-800/60 dark:bg-purple-950/30">
          <p className="mb-2 text-xs font-semibold text-purple-600 dark:text-purple-400">
            {'\uD83E\uDDE0'} Profil Psikografis Rektor
          </p>
          <p className="text-sm text-purple-900 dark:text-purple-200 leading-relaxed whitespace-pre-line">
            {rd.psychographics}
          </p>
          <SourceChip url={rd.psychographics_source} />
        </div>
      )}

      {/* Notes */}
      {rd.notes && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-800/50 dark:bg-amber-950/20">
          <p className="mb-1 text-xs font-medium text-amber-600 dark:text-amber-400">{'\uD83D\uDCDD'} Catatan</p>
          <p className="text-sm italic text-gray-600 dark:text-gray-300 leading-relaxed">
            {rd.notes}
          </p>
        </div>
      )}

      {/* Legacy flat sources (older records) */}
      {rd.sources && rd.sources.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium text-gray-500 dark:text-gray-400">{'\uD83D\uDD17'} Sumber Lainnya</p>
          <div className="flex flex-wrap gap-2">
            {rd.sources.map((src, i) => (
              <SourceChip key={i} url={src} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export function DmsResearchCard({ scheduleId, source, universityName }: DmsResearchCardProps) {
  const { data, isLoading, refetch } = useDmsResearchBySchedule(scheduleId)
  const triggerResearch = useTriggerResearch()
  const [isPollingForResult, setIsPollingForResult] = useState(false)
  const triggerTimestampRef = useRef<number>(0)

  // Fast-poll every 3s while waiting for AI result
  useEffect(() => {
    if (!isPollingForResult) return
    const id = setInterval(() => refetch(), 3000)
    return () => clearInterval(id)
  }, [isPollingForResult, refetch])

  const research = data?.status === 'ok' ? data?.data : null
  const rd = research?.research_data ?? null

  // Stop polling only when a FRESH result arrives (newer than the trigger time)
  useEffect(() => {
    if (!isPollingForResult || !research) return
    const researchedAt = new Date(research.researched_at ?? 0).getTime()
    if (researchedAt > triggerTimestampRef.current) {
      setIsPollingForResult(false)
    }
  }, [research, isPollingForResult])

  const handleTrigger = () => {
    triggerTimestampRef.current = Date.now()
    setIsPollingForResult(false) // reset so effect guard works cleanly
    triggerResearch.mutate(
      { id: scheduleId, source },
      {
        onSuccess: () => setIsPollingForResult(true),
      },
    )
  }

  const showLoading = isPollingForResult || triggerResearch.isPending

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <CardTitle>
            <GraduationCap className="mr-2 inline h-5 w-5 text-indigo-500" />
            Riset Background Rektor
          </CardTitle>
          <div className="flex items-center gap-2 flex-shrink-0">
            {research && !showLoading && (
              <span className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                {new Date(research.researched_at ?? '').toLocaleDateString('id-ID', {
                  day: 'numeric',
                  month: 'short',
                  year: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </span>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={handleTrigger}
              disabled={showLoading}
              title={research ? 'Riset ulang' : 'Mulai riset'}
            >
              {showLoading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : research ? (
                <RefreshCw className="h-3.5 w-3.5" />
              ) : (
                <Search className="h-3.5 w-3.5" />
              )}
              <span className="ml-1">
                {showLoading ? 'Memproses\u2026' : research ? 'Riset Ulang' : 'Mulai Riset'}
              </span>
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        {isLoading ? (
          <div className="flex items-center justify-center py-8 text-gray-400">
            <Loader2 className="h-5 w-5 animate-spin mr-2" />
            <span className="text-sm">Memuat…</span>
          </div>
        ) : showLoading ? (
          <ResearchingOverlay />
        ) : !research || !rd ? (
          <div className="flex flex-col items-center justify-center gap-3 py-10 text-center text-gray-500 dark:text-gray-400">
            <GraduationCap className="h-10 w-10 text-gray-300 dark:text-gray-600" />
            <p className="text-sm font-medium">Belum ada data riset</p>
            <p className="text-xs text-gray-400">
              Klik "Mulai Riset" untuk mendapatkan informasi latar belakang rektor{" "}
              {universityName ?? "universitas ini"}.
            </p>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleTrigger}
              disabled={showLoading}
              className="mt-1"
            >
              <Search className="h-3.5 w-3.5 mr-1" />
              Mulai Riset Sekarang
            </Button>
          </div>
        ) : (
          <ResearchBody rd={rd} research={research} />
        )}
      </CardContent>
    </Card>
  )
}
