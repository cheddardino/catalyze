import Link from 'next/link'
import { createClient } from '@/lib/supabase-server'
import { ColorWheelChart } from '@/components/ColorWheelChart'
import { CleanNowButton } from '@/components/CleanNowButton'

function formatTime(ts: string) {
  return new Date(ts).toLocaleString('en-PH', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit',
    timeZone: 'Asia/Manila',
  })
}

function formatDateLabel(ts: string) {
  return new Date(ts).toLocaleDateString('en-US', {
    month: 'long', day: 'numeric', year: 'numeric',
  })
}

const CONSISTENCY_LABELS: Record<string, string> = {
  Hard:   'Hard',
  Soft:   'Soft',
  Watery: 'Watery',
}

const CONSISTENCY_BAR_COLORS: Record<string, string> = {
  Hard:   '#5CB11A',
  Soft:   '#EE7B00',
  Watery: '#B52E2E',
}

function ConsistencyBars({ counts }: { counts: Record<string, number> }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0)
  const kinds = ['Hard', 'Soft', 'Watery']

  return (
    <div className="flex flex-col gap-1">
      {kinds.map(k => {
        const pct = total > 0 ? (counts[k] ?? 0) / total * 100 : 0
        return (
          <div key={k} className="flex items-center gap-2">
            <span className="text-[11px] font-semibold w-10 text-right flex-shrink-0" style={{ color: '#404040' }}>
              {k}
            </span>
            <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: '#F0F0F0' }}>
              <div
                className="h-full rounded-full transition-all duration-700 ease-out"
                style={{
                  width: `${pct}%`,
                  backgroundColor: CONSISTENCY_BAR_COLORS[k],
                }}
              />
            </div>
            <span className="text-[11px] font-semibold w-4 text-left flex-shrink-0" style={{ color: '#404040' }}>
              {counts[k] ?? 0}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function ColorDots({ colors }: { colors: { brown: number; orange: number; green: number; red: number } }) {
  const sorted = [
    { color: '#7B3B00', value: colors.brown },
    { color: '#EE7B00', value: colors.orange },
    { color: '#5CB11A', value: colors.green },
    { color: '#B52E2E', value: colors.red },
  ].sort((a, b) => b.value - a.value)

  return (
    <div className="flex items-center gap-1.5 mt-0.5">
      {sorted.map((d, i) => (
        <div
          key={i}
          className="w-4 h-4 rounded-full border border-white"
          style={{ backgroundColor: d.color, boxShadow: '0 0 0 0.5px rgba(0,0,0,0.08)' }}
        />
      ))}
    </div>
  )
}

function ConsistencyTag({ kind }: { kind: string | null }) {
  const label = kind ? (CONSISTENCY_LABELS[kind] ?? kind) : 'Unknown'
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold w-fit"
      style={{ backgroundColor: '#9BF5FF', color: '#404040', letterSpacing: '-0.02em' }}
    >
      {label}
    </span>
  )
}

export default async function DashboardPage() {
  const supabase = createClient()

  // Get logged-in user for the Clean Now button
  const { data: { user } } = await supabase.auth.getUser()
  const userEmail = user?.email ?? null

  const now = new Date()
  const todayStr = now.toISOString().slice(0, 10)
  const todayLabel = formatDateLabel(now.toISOString())

  const [{ count: todayCount, data: todayData }, { data: recent }] = await Promise.all([
    supabase
      .from('detections')
      .select('kind, red_pct, yellow_pct, green_pct, brown_pct', { count: 'exact' })
      .gte('timestamp', todayStr),
    supabase
      .from('detections')
      .select('id, timestamp, kind, image_cat, red_pct, yellow_pct, green_pct, brown_pct')
      .order('timestamp', { ascending: false })
      .limit(5),
  ])

  const cycles = todayCount ?? 0

  const colorAvg = { brown: 0, orange: 0, green: 0, red: 0 }
  if (todayData && todayData.length > 0) {
    const n = todayData.length
    for (const d of todayData) {
      colorAvg.brown  += (d.brown_pct  ?? 0) / n
      colorAvg.orange += (d.yellow_pct ?? 0) / n
      colorAvg.green  += (d.green_pct  ?? 0) / n
      colorAvg.red    += (d.red_pct    ?? 0) / n
    }
  }

  const consistencyCounts: Record<string, number> = { Hard: 0, Soft: 0, Watery: 0 }
  if (todayData) {
    for (const d of todayData) {
      if (d.kind && d.kind in consistencyCounts) consistencyCounts[d.kind]++
    }
  }

  const hasUnusual = recent?.some(d => d.red_pct && d.red_pct > 20) ?? false

  return (
    <div className="space-y-4">
      {/* Header — fadeInUp immediately */}
      <header className="flex items-center gap-3 px-0.5 opacity-0 animate-fadeInUp">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.png" alt="Catalyze" className="w-8 h-8 object-contain flex-shrink-0" />
        <h1
          className="text-[28px] font-semibold tracking-tight"
          style={{ color: '#404040', letterSpacing: '-0.02em' }}
        >
          Dashboard
        </h1>
      </header>

      {/* Stats card — fadeInUp, slight delay */}
      <section
        className="bg-white mx-0 opacity-0 animate-fadeInUp animation-delay-100"
        style={{ borderRadius: 20, boxShadow: '0 4px 16px rgba(0,0,0,0.06)', padding: '16px' }}
      >
        {/* Top row: Cleaning Cycles + Activity Overview */}
        <div className="flex gap-4">
          {/* Cleaning Cycles */}
          <div className="flex-1 flex flex-col justify-center">
            <span className="text-lg font-semibold" style={{ color: '#2ECC71', letterSpacing: '-0.02em' }}>
              Today
            </span>
            <span className="text-5xl font-bold leading-tight" style={{ color: '#404040', letterSpacing: '-0.03em' }}>
              {String(cycles).padStart(2, '0')}
            </span>
            <span className="text-[11px] font-semibold" style={{ color: '#666666' }}>
              Cleaning Cycles
            </span>
          </div>

          {/* Activity Overview + Consistency */}
          <div className="flex-[1.3]">
            <h3 className="text-base font-semibold leading-tight" style={{ color: '#404040', letterSpacing: '-0.02em' }}>
              Daily Activity Overview
            </h3>
            <p className="text-xs mb-2" style={{ color: '#666666' }}>{todayLabel}</p>
            <ConsistencyBars counts={consistencyCounts} />
            <p className="text-[11px] font-semibold text-center mt-1" style={{ color: '#E28331' }}>
              Consistency
            </p>
          </div>
        </div>

        {/* Divider */}
        <div className="my-3 h-px" style={{ backgroundColor: '#F0F0F0' }} />

        {/* Bottom row: Donut chart + Color indicators */}
        <div className="flex gap-4 items-center">
          {/* Donut chart */}
          <div className="flex-1 flex flex-col items-center">
            <div className="relative w-20 h-20">
              <ColorWheelChart
                brown={Math.round(colorAvg.brown)}
                orange={Math.round(colorAvg.orange)}
                green={Math.round(colorAvg.green)}
                red={Math.round(colorAvg.red)}
              />
            </div>
            <span className="text-[11px] font-semibold mt-1" style={{ color: '#E28331' }}>
              Detected Colors
            </span>
          </div>

          {/* Color legend + status */}
          <div className="flex-[1.3]">
            <div className="flex flex-col gap-1.5">
              {[
                { label: 'Brown',  color: '#7B3B00', value: Math.round(colorAvg.brown) },
                { label: 'Orange', color: '#EE7B00', value: Math.round(colorAvg.orange) },
                { label: 'Green',  color: '#5CB11A', value: Math.round(colorAvg.green) },
                { label: 'Red',    color: '#B52E2E', value: Math.round(colorAvg.red) },
              ].map(item => (
                <div key={item.label} className="flex items-center gap-2">
                  <div
                    className="w-3 h-3 rounded-full border border-white"
                    style={{ backgroundColor: item.color, boxShadow: '0 0 0 1px rgba(255,255,255,0.8)' }}
                  />
                  <span className="text-xs font-medium" style={{ color: '#404040' }}>
                    {item.value}%
                  </span>
                </div>
              ))}
            </div>
            <p className="text-sm font-medium mt-2 text-right" style={{ color: '#666666' }}>
              {hasUnusual ? 'Unusual activity!' : 'No unusual activity!'}
            </p>
          </div>
        </div>
      </section>

      {/* Action buttons row — Clean Now */}
      {userEmail && (
        <section
          className="mx-0 opacity-0 animate-fadeInUp animation-delay-200 space-y-3"
        >
          <div
            className="bg-white"
            style={{ borderRadius: 20, boxShadow: '0 4px 16px rgba(0,0,0,0.06)', padding: '16px' }}
          >
            <CleanNowButton userEmail={userEmail} />
          </div>
        </section>
      )}

      {/* Recent Detection heading — fadeInUp, delay 300 */}
      <h2
        className="text-xl font-semibold px-0.5 opacity-0 animate-fadeInUp animation-delay-300"
        style={{ color: '#404040', letterSpacing: '-0.02em' }}
      >
        Recent Detection:
      </h2>

      {/* Cards */}
      <div className="flex flex-col gap-3">
        {(!recent || recent.length === 0) && (
          <div
            className="bg-white flex items-center justify-center py-8 opacity-0 animate-fadeInUp animation-delay-300"
            style={{ borderRadius: 12, boxShadow: '0 4px 16px rgba(0,0,0,0.06)' }}
          >
            <p className="text-sm" style={{ color: '#666666' }}>No detections yet</p>
          </div>
        )}

        {recent?.map((item, index) => {
          const colors = {
            brown:  item.brown_pct  ?? 0,
            orange: item.yellow_pct ?? 0,
            green:  item.green_pct  ?? 0,
            red:    item.red_pct    ?? 0,
          }
          return (
            <Link
              key={item.id}
              href={`/activity/${item.id}`}
              className="flex items-center gap-3 rounded-xl px-3 py-2.5 transition-all duration-200 hover:scale-[1.01] opacity-0 animate-fadeInUp"
              style={{
                backgroundColor: '#FFFFFF',
                boxShadow: '0 4px 16px rgba(0,0,0,0.06)',
                animationDelay: `${(index + 4) * 100}ms`,
              }}
            >
              <div className="w-12 h-12 rounded-lg overflow-hidden flex-shrink-0" style={{ backgroundColor: '#F0F0F0' }}>
                {(item as Record<string, unknown>).image_cat ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={(item as Record<string, unknown>).image_cat as string} alt="" className="w-full h-full object-cover" />
                ) : (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src="/cat-icon-overview.png" alt="" className="w-full h-full object-contain p-1" />
                )}
              </div>

              <div className="flex flex-col gap-0.5">
                <span className="text-xs font-semibold" style={{ color: '#404040', letterSpacing: '-0.02em' }}>
                  {formatTime(item.timestamp)}
                </span>
                <ConsistencyTag kind={item.kind} />
                <ColorDots colors={colors} />
              </div>
            </Link>
          )
        })}
      </div>

      {recent && recent.length > 0 && (
        <div className="text-center opacity-0 animate-fadeInUp" style={{ animationDelay: `${(Math.min((recent?.length ?? 0), 5) + 4) * 100}ms` }}>
          <Link href="/activity" className="text-sm font-medium" style={{ color: '#E28331' }}>
            View all activity →
          </Link>
        </div>
      )}
    </div>
  )
}
