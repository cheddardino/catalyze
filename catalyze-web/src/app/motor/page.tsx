import { unstable_noStore as noStore } from 'next/cache'
import { createClient } from '@/lib/supabase-server'
import { MotorActionButtons } from '@/components/MotorActionButtons'

type State = 'MONITORING' | 'OCCUPIED' | 'CHECKING' | 'DIRTY' | 'COOLDOWN' | 'OFFLINE' | string

const STATE_LABELS: Record<string, string> = {
  MONITORING: 'Monitoring',
  OCCUPIED:   'Cat Inside',
  CHECKING:   'Scanning',
  DIRTY:      'Dirty — Cleaning',
  COOLDOWN:   'Cooldown',
  OFFLINE:    'Offline',
}

const STATE_COLORS: Record<string, string> = {
  MONITORING: '#5CB11A',
  OCCUPIED:   '#E28331',
  CHECKING:   '#E28331',
  DIRTY:      '#B52E2E',
  COOLDOWN:   '#5CB11A',
  OFFLINE:    '#9CA3AF',
}

function LedIndicators({ state }: { state: State }) {
  const greenOn  = state === 'MONITORING' || state === 'COOLDOWN'
  const yellowOn = state === 'OCCUPIED'   || state === 'CHECKING'
  const redOn    = state === 'DIRTY'

  return (
    <div className="flex items-center gap-4">
      {[
        { label: 'GPIO 13', on: greenOn,  color: '#5CB11A', offColor: '#D1FAE5' },
        { label: 'GPIO 6',  on: yellowOn, color: '#F59E0B', offColor: '#FEF3C7' },
        { label: 'GPIO 5',  on: redOn,    color: '#EF4444', offColor: '#FEE2E2' },
      ].map(({ label, on, color, offColor }) => (
        <div key={label} className="flex flex-col items-center gap-1.5">
          <div
            className="w-5 h-5 rounded-full border-2 border-white"
            style={{
              backgroundColor: on ? color : offColor,
              boxShadow: on ? `0 0 10px ${color}80, 0 0 4px ${color}` : 'none',
              transition: 'all 0.3s ease',
            }}
          />
          <span className="text-[10px] font-medium text-gray-400">{label}</span>
        </div>
      ))}
    </div>
  )
}

function StatusBadge({ state }: { state: State }) {
  const label = STATE_LABELS[state] ?? state
  const color = STATE_COLORS[state] ?? '#9CA3AF'
  const isOffline = state === 'OFFLINE'
  return (
    <div className="flex items-center gap-2">
      <span
        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
        style={{
          backgroundColor: color,
          boxShadow: isOffline ? 'none' : `0 0 6px ${color}80`,
          animation: state === 'DIRTY' || state === 'CHECKING' ? 'pulse 1.5s infinite' : 'none',
        }}
      />
      <span className="text-base font-semibold" style={{ color }}>
        {label}
      </span>
    </div>
  )
}

function timeAgo(ts: string): string {
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000)
  if (diff < 5)   return 'just now'
  if (diff < 60)  return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return `${Math.floor(diff / 3600)}h ago`
}

function formatTime(ts: string) {
  return new Date(ts).toLocaleString('en-PH', {
    month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
    timeZone: 'Asia/Manila',
  })
}

const CMD_STATUS_STYLE: Record<string, { bg: string; color: string; label: string }> = {
  pending: { bg: '#FEF3C7', color: '#92400E', label: 'Pending' },
  running: { bg: '#DBEAFE', color: '#1E40AF', label: 'Running' },
  done:    { bg: '#D1FAE5', color: '#065F46', label: 'Done' },
  failed:  { bg: '#FEE2E2', color: '#991B1B', label: 'Failed' },
}

const CMD_TYPE_STYLE: Record<string, { label: string; color: string; bg: string }> = {
  clean:      { label: 'Clean',       color: '#92400E', bg: '#FEF3C7' },
  cw:         { label: 'CW',          color: '#1E40AF', bg: '#DBEAFE' },
  ccw:        { label: 'CCW',         color: '#1D4ED8', bg: '#DBEAFE' },
  full_cycle: { label: 'Full Cycle',  color: '#065F46', bg: '#D1FAE5' },
}

const DEVICE_ONLINE_WINDOW_MS = 20_000

export default async function MotorPage() {
  noStore()

  const supabase = createClient()

  const { data: { user } } = await supabase.auth.getUser()
  const userEmail = user?.email ?? null

  const [{ data: statusRow }, { data: commands }] = await Promise.all([
    supabase
      .from('device_status')
      .select('state, updated_at')
      .eq('id', 1)
      .single(),
    supabase
      .from('commands')
      .select('id, type, status, triggered_by, created_at, executed_at')
      .order('created_at', { ascending: false })
      .limit(10),
  ])

  const state: State = (statusRow?.state as State) ?? 'OFFLINE'
  const updatedAt    = statusRow?.updated_at ?? null
  const updatedAtMs   = updatedAt ? new Date(updatedAt).getTime() : 0
  const isFresh       = updatedAtMs > 0 && (Date.now() - updatedAtMs) < DEVICE_ONLINE_WINDOW_MS
  const isOnline      = state !== 'OFFLINE' && isFresh
  const displayState: State = isOnline ? state : 'OFFLINE'

  return (
    <div className="space-y-4">
      <header className="flex items-center gap-3 px-0.5">
        <div
          className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
          style={{ background: 'linear-gradient(135deg, #E28331, #C96A1F)' }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth={2} className="w-4 h-4">
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M11.42 15.17L17.25 21A2.652 2.652 0 0021 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 11-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 004.486-6.336l-3.276 3.277a3.004 3.004 0 01-2.25-2.25l3.276-3.276a4.5 4.5 0 00-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437l1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008z" />
          </svg>
        </div>
        <h1 className="text-[28px] font-semibold tracking-tight" style={{ color: '#404040', letterSpacing: '-0.02em' }}>
          Motor Control
        </h1>
      </header>

      {/* Device Status */}
      <section className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 space-y-4">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Device Status</p>
            <StatusBadge state={displayState} />
            {updatedAt && (
              <p className="text-xs text-gray-400 mt-0.5">
                Updated {timeAgo(updatedAt)}{isFresh ? ' · live' : ''}
              </p>
            )}
          </div>
          <div className="flex flex-col items-end gap-2">
            <LedIndicators state={displayState} />
            <p className="text-[10px] text-gray-400 text-right">Status LEDs</p>
          </div>
        </div>

        {!isOnline && (
          <div className="bg-amber-50 rounded-xl px-3 py-2.5 flex items-start gap-2">
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5">
              <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
            </svg>
            <p className="text-xs text-amber-700">
              Device is offline. Commands will queue and execute when the Pi reconnects.
            </p>
          </div>
        )}
      </section>

      {/* Manual Control (Clean Now button removed) */}
      {userEmail && (
        <section className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 space-y-3">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Manual Control</p>
          <MotorActionButtons />
          <div className="flex items-center gap-2 pt-1">
            <div className="w-2 h-2 rounded-full bg-gray-300 flex-shrink-0" />
            <p className="text-xs text-gray-400">
              Physical button on <span className="font-semibold text-gray-500">GPIO 0</span> also triggers a cleaning cycle.
            </p>
          </div>
        </section>
      )}

      {/* Motor Specs */}
      <section className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 space-y-3">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Motor Config</p>
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: 'Direction', value: 'CW' },
            { label: 'Steps', value: '2 000' },
            { label: 'Step Delay', value: '1.5 ms' },
          ].map(({ label, value }) => (
            <div key={label} className="bg-gray-50 rounded-xl p-2.5 text-center">
              <p className="text-base font-bold text-gray-800">{value}</p>
              <p className="text-[10px] text-gray-400 mt-0.5">{label}</p>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: 'DIR+ pin', value: 'GPIO 17' },
            { label: 'PUL+ pin', value: 'GPIO 27' },
          ].map(({ label, value }) => (
            <div key={label} className="bg-gray-50 rounded-xl p-2.5 text-center">
              <p className="text-sm font-bold text-gray-800">{value}</p>
              <p className="text-[10px] text-gray-400 mt-0.5">{label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Recent Commands */}
      <section className="space-y-2">
        <h2 className="text-base font-semibold px-0.5" style={{ color: '#404040' }}>Recent Commands</h2>
        {(!commands || commands.length === 0) ? (
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 text-center">
            <p className="text-sm text-gray-400">No commands yet</p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {commands.map(cmd => {
              const style = CMD_STATUS_STYLE[cmd.status] ?? CMD_STATUS_STYLE.pending
              const typeStyle = CMD_TYPE_STYLE[cmd.type] ?? { label: cmd.type, color: '#374151', bg: '#F3F4F6' }
              const triggeredBy = cmd.triggered_by === 'button' ? 'Physical button' : (cmd.triggered_by ?? 'App')
              return (
                <div
                  key={cmd.id}
                  className="bg-white rounded-xl border border-gray-100 shadow-sm px-4 py-3 flex items-center gap-3"
                >
                  <div
                    className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
                    style={{ backgroundColor: style.bg }}
                  >
                    {cmd.status === 'done' ? (
                      <svg viewBox="0 0 20 20" fill={style.color} className="w-4 h-4">
                        <path fillRule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clipRule="evenodd" />
                      </svg>
                    ) : cmd.status === 'failed' ? (
                      <svg viewBox="0 0 20 20" fill={style.color} className="w-4 h-4">
                        <path fillRule="evenodd" d="M4 10a6 6 0 1112 0A6 6 0 014 10zm7.75-2.25a.75.75 0 00-1.5 0v2.5a.75.75 0 001.5 0v-2.5zM10 14a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
                      </svg>
                    ) : cmd.status === 'running' ? (
                      <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke={style.color} strokeWidth="4" />
                        <path className="opacity-75" fill={style.color} d="M4 12a8 8 0 018-8v4l3-3-3-3v4a10 10 0 100 10z" />
                      </svg>
                    ) : (
                      <svg viewBox="0 0 20 20" fill={style.color} className="w-4 h-4">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm.75-11.25a.75.75 0 00-1.5 0v4.59L7.3 9.24a.75.75 0 00-1.1 1.02l3.25 3.5a.75.75 0 001.1 0l3.25-3.5a.75.75 0 10-1.1-1.02l-1.95 2.1V6.75z" clipRule="evenodd" />
                      </svg>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span
                        className="text-[11px] font-semibold px-2 py-0.5 rounded-full"
                        style={{ backgroundColor: style.bg, color: style.color }}
                      >
                        {style.label}
                      </span>
                      <span
                        className="text-[11px] font-semibold px-2 py-0.5 rounded-full"
                        style={{ backgroundColor: typeStyle.bg, color: typeStyle.color }}
                      >
                        {typeStyle.label}
                      </span>
                      <span className="text-xs text-gray-400 truncate">{triggeredBy}</span>
                    </div>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {formatTime(cmd.created_at)}
                      {cmd.executed_at && cmd.status === 'done' && (
                        <> · finished {timeAgo(cmd.executed_at)}</>
                      )}
                    </p>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}
