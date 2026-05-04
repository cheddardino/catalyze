'use client'

import { useState, useEffect } from 'react'
import { createClient } from '@/lib/supabase'

type AdminUser = {
  email: string
  is_admin: boolean
  created_at: string
}

type Message = { type: 'success' | 'error'; text: string }

export default function AdminPage() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [newAdminEmail, setNewAdminEmail] = useState('')
  const [message, setMessage] = useState<Message | null>(null)
  const [loading, setLoading] = useState(true)
  const [isAdmin, setIsAdmin] = useState(false)

  const supabase = createClient()

  useEffect(() => {
    checkAdminAccess()
  }, [])

  async function checkAdminAccess() {
    try {
      const {
        data: { user },
      } = await supabase.auth.getUser()

      if (!user?.email) {
        setMessage({ type: 'error', text: 'Not authenticated' })
        setLoading(false)
        return
      }

      const response = await fetch('/api/admin')
      if (response.status === 403) {
        setMessage({ type: 'error', text: 'Admin access required' })
        setIsAdmin(false)
        setLoading(false)
        return
      }

      if (!response.ok) {
        throw new Error('Failed to fetch admin data')
      }

      const data = await response.json()
      setUsers(data.users || [])
      setIsAdmin(true)
    } catch (err) {
      setMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'An error occurred',
      })
    } finally {
      setLoading(false)
    }
  }

  async function grantAdmin() {
    if (!newAdminEmail.trim()) {
      setMessage({ type: 'error', text: 'Please enter an email' })
      return
    }

    try {
      const response = await fetch('/api/admin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'grant_admin', target_email: newAdminEmail }),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.error || 'Failed to grant admin')
      }

      setMessage({ type: 'success', text: `✓ Admin granted to ${newAdminEmail}` })
      setNewAdminEmail('')
      checkAdminAccess()
    } catch (err) {
      setMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'An error occurred',
      })
    }
  }

  async function revokeAdmin(email: string) {
    if (!confirm(`Remove admin status from ${email}?`)) return

    try {
      const response = await fetch('/api/admin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'revoke_admin', target_email: email }),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.error || 'Failed to revoke admin')
      }

      setMessage({ type: 'success', text: `✓ Admin removed from ${email}` })
      checkAdminAccess()
    } catch (err) {
      setMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'An error occurred',
      })
    }
  }

  if (loading) {
    return <div className="p-4">Loading...</div>
  }

  if (!isAdmin) {
    return (
      <div className="p-4 bg-red-100 border border-red-400 rounded">
        <p className="text-red-700">⚠ Admin access required. Contact your administrator.</p>
      </div>
    )
  }

  return (
    <main className="max-w-2xl mx-auto p-4 sm:p-6">
      <h1 className="text-2xl font-bold mb-6">Admin Settings</h1>

      {message && (
        <div
          className={`p-4 rounded mb-6 ${
            message.type === 'success'
              ? 'bg-green-100 text-green-800 border border-green-300'
              : 'bg-red-100 text-red-800 border border-red-300'
          }`}
        >
          {message.text}
        </div>
      )}

      {/* Grant Admin Section */}
      <section className="bg-white p-6 rounded-lg shadow mb-6">
        <h2 className="text-lg font-semibold mb-4">Grant Admin Access</h2>
        <div className="flex gap-2">
          <input
            type="email"
            placeholder="Enter email address"
            value={newAdminEmail}
            onChange={(e) => setNewAdminEmail(e.target.value)}
            className="flex-1 px-4 py-2 border border-gray-300 rounded"
          />
          <button
            onClick={grantAdmin}
            className="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 font-medium"
          >
            Grant Admin
          </button>
        </div>
      </section>

      {/* Current Admins Section */}
      <section className="bg-white p-6 rounded-lg shadow">
        <h2 className="text-lg font-semibold mb-4">Administrators ({users.filter((u) => u.is_admin).length})</h2>
        <div className="space-y-3">
          {users
            .filter((u) => u.is_admin)
            .map((user) => (
              <div key={user.email} className="flex items-center justify-between bg-gray-50 p-4 rounded">
                <div>
                  <p className="font-medium">{user.email}</p>
                  <p className="text-sm text-gray-600">
                    Admin since{' '}
                    {new Date(user.created_at).toLocaleDateString('en-PH', {
                      year: 'numeric',
                      month: 'short',
                      day: 'numeric',
                    })}
                  </p>
                </div>
                <button
                  onClick={() => revokeAdmin(user.email)}
                  className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 text-sm font-medium"
                >
                  Remove
                </button>
              </div>
            ))}
        </div>

        {users.filter((u) => u.is_admin).length === 0 && (
          <p className="text-gray-500 italic">No admins yet</p>
        )}
      </section>

      {/* Regular Users Section */}
      <section className="bg-white p-6 rounded-lg shadow mt-6">
        <h2 className="text-lg font-semibold mb-4">Regular Users ({users.filter((u) => !u.is_admin).length})</h2>
        <div className="space-y-3">
          {users
            .filter((u) => !u.is_admin)
            .map((user) => (
              <div key={user.email} className="flex items-center justify-between bg-gray-50 p-4 rounded">
                <div>
                  <p className="font-medium">{user.email}</p>
                  <p className="text-sm text-gray-600">
                    Joined{' '}
                    {new Date(user.created_at).toLocaleDateString('en-PH', {
                      year: 'numeric',
                      month: 'short',
                      day: 'numeric',
                    })}
                  </p>
                </div>
                <button
                  onClick={() => grantAdmin()}
                  className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 text-sm font-medium"
                >
                  Make Admin
                </button>
              </div>
            ))}
        </div>

        {users.filter((u) => !u.is_admin).length === 0 && (
          <p className="text-gray-500 italic">No regular users yet</p>
        )}
      </section>
    </main>
  )
}
