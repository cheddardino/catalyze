'use client'

import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import { supabase, type Detection } from '@/lib/supabase'
import { ConsistencyBadge } from '@/components/ConsistencyBadge'
import { SeverityBadge } from '@/components/SeverityBadge'

const PAGE_SIZE = 20

/** Format ISO date string to Manila local time display */
function formatTime(ts: string) {
  return new Date(ts).toLocaleString('en-PH', {
    month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
    timeZone: 'Asia/Manila',
  })
}

/** Today's date in Asia/Manila as YYYY-MM-DD */
function todayManila(): string {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Manila' })
}

type Row = Pick<Detection, 'id' | 'timestamp' | 'kind' | 'severity' | 'remark'>
type ConsistencyFilter = 'All' | 'Firm' | 'Soft' | 'Watery'

const dbKind: Record<ConsistencyFilter, string | null> = {
  All: null,
  Firm: 'Hard',
  Soft: 'Soft',
  Watery: 'Watery',
}

export default function ActivityPage() {
  const [selectedDate, setSelectedDate] = useState<string>(todayManila())
  const [filter, setFilter] = useState<ConsistencyFilter>('All')
  const [items, setItems] = useState<Row[]>([])
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(false)
  const [hasMore, setHasMore] = useState(true)
  const [showPicker, setShowPicker] = useState(false)
  const [allTime, setAllTime] = useState(false)

  const load = useCallback(async (
    date: string,
    f: ConsistencyFilter,
    off: number,
    replace: boolean,
    all: boolean = false,
  ) => {
    setLoading(true)
    let q = supabase.from('detections').select('id, timestamp, kind, severity, remark')
      .order('timestamp', { ascending: false })
      .range(off, off + PAGE_SIZE - 1)

    // If not showing all-time, filter by selected Manila date (converted to UTC range)
    if (!all) {
      const startUtc = new Date(`${date}T00:00:00+08:00`).toISOString()
      const endUtc   = new Date(`${date}T23:59:59.999+08:00`).toISOString()
      q = q.gte('timestamp', startUtc).lte('timestamp', endUtc)
    }

    const kind = dbKind[f]
    if (kind) q = q.eq('kind', kind)

    const { data } = await q
    const rows = (data ?? []) as Row[]
    setItems(prev => replace ? rows : [...prev, ...rows])
    setHasMore(rows.length === PAGE_SIZE)
    setLoading(false)
  }, [])

  useEffect(() => {
    setOffset(0)
    setHasMore(true)
    load(selectedDate, filter, 0, true, allTime)
  }, [selectedDate, filter, load, allTime])

  const loadMore = () => {
    const next = offset + PAGE_SIZE
    setOffset(next)
    load(selectedDate, filter, next, false, allTime)
  }

  function handleDateChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value
    if (val && val <= todayManila()) {
      setSelectedDate(val)
      setShowPicker(false)
    }
  }

  const today = todayManila()
  const isToday = selectedDate === today

  const displayDate = new Date(`${selectedDate}T12:00:00`).toLocaleDateString('en-PH', {
    weekday: 'short', month: 'long', day: 'numeric', year: 'numeric',
  })

  const filters: ConsistencyFilter[] = ['All', 'Firm', 'Soft', 'Watery']

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold text-gray-900 text-center">Activity Log</h1>

      {/* Date selector */}
      <div className="relative flex items-center justify-center">
        <button
          onClick={() => setShowPicker(v => !v)}
          className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-xl text-sm font-medium text-gray-700 hover:border-brand-300 transition-colors shadow-sm"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-brand-500">
            <path fillRule="evenodd" d="M5.75 2a.75.75 0 01.75.75V4h7V2.75a.75.75 0 011.5 0V4h.25A2.75 2.75 0 0118 6.75v8.5A2.75 2.75 0 0115.25 18H4.75A2.75 2.75 0 012 15.25v-8.5A2.75 2.75 0 014.75 4H5V2.75A.75.75 0 015.75 2zm-1 5.5c-.69 0-1.25.56-1.25 1.25v6.5c0 .69.56 1.25 1.25 1.25h10.5c.69 0 1.25-.56 1.25-1.25v-6.5c0-.69-.56-1.25-1.25-1.25H4.75z" clipRule="evenodd" />
          </svg>
          <span>{isToday ? 'Today' : displayDate}</span>
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5 text-gray-400">
            <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
          </svg>
        </button>

        {showPicker && (
          <div className="absolute top-full mt-1 z-20 bg-white border border-gray-200 rounded-2xl shadow-lg p-3">
            <input
              type="date"
              value={selectedDate}
              max={today}
              onChange={handleDateChange}
              className="block px-3 py-2 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
            {selectedDate !== today && (
              <button
                onClick={() => { setSelectedDate(today); setShowPicker(false) }}
                className="mt-2 w-full py-1.5 text-xs text-brand-600 font-medium hover:bg-brand-50 rounded-lg transition-colors"
              >
                Back to today
              </button>
            )}
          </div>
        )}
      </div>

      {/* Consistency filter pills (+ All-time toggle) */}
      <div className="flex gap-2 flex-wrap justify-center items-center">
        <button
          onClick={() => {
            // toggle all-time view
            setAllTime(v => !v)
            setOffset(0)
            setHasMore(true)
            setItems([])
          }}
          className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors mr-1 ${
            allTime ? 'bg-brand-500 text-white' : 'bg-white border border-gray-200 text-gray-600 hover:border-brand-300'
          }`}
        >
          All-time
        </button>

        <div className="flex items-center gap-2">
        {filters.map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
              filter === f
                ? 'bg-brand-500 text-white'
                : 'bg-white border border-gray-200 text-gray-600 hover:border-brand-300'
            }`}
          >
            {f}
          </button>
        ))}
        </div>
      </div>

      {/* List */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 divide-y divide-gray-50">
        {items.length === 0 && !loading && (
          <div className="p-8 text-center space-y-1">
            <p className="text-gray-400 text-sm font-medium">No detections on this day</p>
            {!isToday && (
              <p className="text-gray-300 text-xs">{displayDate}</p>
            )}
          </div>
        )}
        {items.map(item => (
          <Link
            key={item.id}
            href={`/activity/${item.id}`}
            className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50 transition-colors"
          >
            <div className="flex-1 min-w-0">
              <p className="text-xs text-gray-400 mb-1">{formatTime(item.timestamp)}</p>
              <div className="flex items-center gap-1.5 flex-wrap">
                <ConsistencyBadge kind={item.kind} />
                {item.severity && item.severity !== 'normal' && (
                  <SeverityBadge severity={item.severity as Detection['severity']} />
                )}
              </div>
              {item.remark && (
                <p className="text-xs text-gray-500 mt-1 truncate">{item.remark}</p>
              )}
            </div>
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-gray-300 flex-shrink-0">
              <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd" />
            </svg>
          </Link>
        ))}

        {loading && (
          <div className="p-6 text-center text-gray-400 text-sm">Loading…</div>
        )}
      </div>

      {hasMore && !loading && items.length > 0 && (
        <button
          onClick={loadMore}
          className="w-full py-3 text-sm text-brand-600 font-medium border border-brand-200 rounded-xl hover:bg-brand-50 transition-colors"
        >
          Load more
        </button>
      )}
    </div>
  )
}
