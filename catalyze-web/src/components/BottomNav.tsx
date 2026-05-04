'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const hideOnRoutes = ['/login', '/signup', '/privacy', '/tos', '/policy', '/terms']

export function BottomNav() {
  const path = usePathname()

  if (hideOnRoutes.includes(path)) return null

  const isHome     = path === '/'
  const isActivity = path.startsWith('/activity') || path.startsWith('/history')
  const isProfile  = path.startsWith('/profile') || path.startsWith('/settings')

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-50 pb-safe"
      style={{ background: '#90D9FB', boxShadow: '0 -2px 12px rgba(0,0,0,0.04)' }}
    >
      {/*
        3-slot layout: [Activity] [HOME-spacer] [Profile]
        justify-around → items at 25% 50% 75%
        HOME is absolutely centered at 50%, sitting over the spacer slot.
      */}
      <div
        className="flex items-end justify-around max-w-lg mx-auto relative"
        style={{ height: 64 }}
      >
        {/* Activity Log */}
        <Link
          href="/activity"
          className="flex flex-col items-center justify-end gap-0.5 transition-opacity pb-2"
          style={{ width: 56, opacity: isActivity ? 1 : 0.55 }}
        >
          <svg viewBox="0 0 24 24" fill={isActivity ? '#E28331' : '#404040'} className="w-6 h-6">
            <path
              fillRule="evenodd"
              d="M5.625 1.5c-1.036 0-1.875.84-1.875 1.875v17.25c0 1.035.84 1.875 1.875 1.875h12.75c1.035 0 1.875-.84 1.875-1.875V12.75A3.75 3.75 0 0016.5 9h-1.875a1.875 1.875 0 01-1.875-1.875V5.25A3.75 3.75 0 009 1.5H5.625zM7.5 15a.75.75 0 01.75-.75h7.5a.75.75 0 010 1.5h-7.5A.75.75 0 017.5 15zm.75 2.25a.75.75 0 000 1.5H12a.75.75 0 000-1.5H8.25z"
              clipRule="evenodd"
            />
            <path d="M12.971 1.816A5.23 5.23 0 0114.25 5.25v1.875c0 .207.168.375.375.375H16.5a5.23 5.23 0 013.434 1.279 9.768 9.768 0 00-6.963-6.963z" />
          </svg>
          <span className="text-[10px] font-semibold leading-none" style={{ color: '#404040' }}>
            Activity
          </span>
        </Link>

        {/* Spacer for HOME circle */}
        <div style={{ width: 65 }} />

        {/* Profile */}
        <Link
          href="/profile"
          className="flex flex-col items-center justify-end gap-0.5 transition-opacity pb-2"
          style={{ width: 56, opacity: isProfile ? 1 : 0.55 }}
        >
          <svg viewBox="0 0 24 24" fill={isProfile ? '#E28331' : '#404040'} className="w-6 h-6">
            <path
              fillRule="evenodd"
              d="M7.5 6a4.5 4.5 0 119 0 4.5 4.5 0 01-9 0zM3.751 20.105a8.25 8.25 0 0116.498 0 .75.75 0 01-.437.695A18.683 18.683 0 0112 22.5c-2.786 0-5.433-.608-7.812-1.7a.75.75 0 01-.437-.695z"
              clipRule="evenodd"
            />
          </svg>
          <span className="text-[10px] font-semibold leading-none" style={{ color: '#404040' }}>
            Profile
          </span>
        </Link>

        {/* Home — elevated orange circle, absolutely centered */}
        <Link
          href="/"
          className="flex flex-col items-center gap-0.5 absolute left-1/2 -translate-x-1/2"
          style={{ bottom: 8 }}
        >
          <div
            className="flex items-center justify-center animate-pulseScale"
            style={{
              width: 65,
              height: 65,
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #E28331, #C96A1F)',
              boxShadow: isHome
                ? '0 6px 20px rgba(226,131,49,0.5)'
                : '0 6px 20px rgba(226,131,49,0.25)',
              border: '3px solid white',
            }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png" alt="Home" style={{ width: 38, height: 38, objectFit: 'contain' }} />
          </div>
          <span className="text-[10px] font-semibold leading-none" style={{ color: '#404040' }}>
            Home
          </span>
        </Link>
      </div>
    </nav>
  )
}
