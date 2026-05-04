'use client'

import { useState, useCallback } from 'react'
import { supabase } from '@/lib/supabase'

type ButtonState = 'idle' | 'pending' | 'done' | 'timeout' | 'error'

const POLL_INTERVAL_MS = 2_000
const TIMEOUT_MS       = 30_000

export function CleanNowButton({ userEmail }: { userEmail: string }) {
  const [btnState, setBtnState] = useState<ButtonState>('idle')

  const handleClean = useCallback(async () => {
    if (btnState !== 'idle') return
    setBtnState('pending')

    const res = await fetch('/api/motor', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'clean' }),
    })

    const payload = await res.json().catch(() => null)

    if (res.status === 403) {
      console.error('[clean] admin access required')
      setBtnState('error')
      alert('⚠ Only administrators can trigger the clean action.')
      setTimeout(() => setBtnState('idle'), 4_000)
      return
    }

    if (!res.ok || !payload?.id) {
      console.error('[clean] enqueue failed', payload)
      setBtnState('error')
      setTimeout(() => setBtnState('idle'), 4_000)
      return
    }

    const cmdId = payload.id
    const deadline = Date.now() + TIMEOUT_MS

    // Poll until done / failed / timeout
    const interval = setInterval(async () => {
      if (Date.now() > deadline) {
        clearInterval(interval)
        setBtnState('timeout')
        setTimeout(() => setBtnState('idle'), 5_000)
        return
      }

      const { data: row } = await supabase
        .from('commands')
        .select('status')
        .eq('id', cmdId)
        .single()

      if (!row) return

      if (row.status === 'done') {
        clearInterval(interval)
        setBtnState('done')
        setTimeout(() => setBtnState('idle'), 4_000)
      } else if (row.status === 'failed') {
        clearInterval(interval)
        setBtnState('error')
        setTimeout(() => setBtnState('idle'), 4_000)
      }
      // 'pending' and 'running' → keep polling
    }, POLL_INTERVAL_MS)
  }, [btnState, userEmail])

  // ── Render ───────────────────────────────────────────────────────────
  const isPending = btnState === 'pending'

  const buttonStyle: React.CSSProperties = {
    background: isPending
      ? 'linear-gradient(135deg, #aaa, #888)'
      : 'linear-gradient(135deg, #E28331, #C96A1F)',
    boxShadow: isPending
      ? 'none'
      : '0 4px 16px rgba(226,131,49,0.35)',
    transition: 'all 0.2s ease',
    cursor: isPending ? 'default' : 'pointer',
  }

  return (
    <div className="space-y-1.5">
      <button
        onClick={handleClean}
        disabled={btnState !== 'idle'}
        style={buttonStyle}
        className="w-full py-3.5 rounded-2xl text-white font-semibold text-sm tracking-wide flex items-center justify-center gap-2 active:scale-[0.98] transition-transform"
      >
        {isPending ? (
          <>
            {/* Spinner */}
            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a10 10 0 100 10l-1.41-1.41A8 8 0 014 12z" />
            </svg>
            Cleaning…
          </>
        ) : (
          <>
            {/* Broom icon */}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 3l14 14M9 9l6 6M3 21l4-4" />
            </svg>
            Clean Now
          </>
        )}
      </button>

      {/* Status messages below the button */}
      {btnState === 'done' && (
        <p className="text-center text-xs font-semibold text-green-600">
          ✓ Cleaning cycle complete.
        </p>
      )}
      {btnState === 'timeout' && (
        <p className="text-center text-xs font-semibold text-amber-600">
          No response from device — is it online?
        </p>
      )}
      {btnState === 'error' && (
        <p className="text-center text-xs font-semibold text-red-500">
          Command failed. Try again.
        </p>
      )}

      {/* Helper note */}
      {btnState === 'idle' && (
        <p className="text-center text-[11px] text-gray-400">
          This triggers one full cleaning rotation of the litter drum.
        </p>
      )}
    </div>
  )
}
