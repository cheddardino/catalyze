import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

function createSupabaseClient() {
  const cookieStore = cookies()
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll()
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options)
          )
        },
      },
    }
  )
}

export async function POST(req: NextRequest) {
  const supabase = createSupabaseClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user?.email) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
  }

  // Check if requester is admin
  const { data: adminCheck } = await supabase
    .from('users')
    .select('is_admin')
    .eq('email', user.email)
    .single()

  if (!adminCheck?.is_admin) {
    return NextResponse.json({ error: 'admin access required' }, { status: 403 })
  }

  let body: { action?: string; target_email?: string }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'invalid json' }, { status: 400 })
  }

  const { action, target_email } = body

  if (!action || !['grant_admin', 'revoke_admin'].includes(action)) {
    return NextResponse.json({ error: 'unsupported action' }, { status: 400 })
  }

  if (!target_email) {
    return NextResponse.json({ error: 'target_email required' }, { status: 400 })
  }

  // Prevent revoking own admin (safety)
  if (action === 'revoke_admin' && target_email === user.email) {
    return NextResponse.json(
      { error: 'cannot revoke your own admin status' },
      { status: 400 }
    )
  }

  // Upsert user and update admin status
  const is_admin = action === 'grant_admin'
  const { error } = await supabase.from('users').upsert({
    email: target_email,
    is_admin,
    updated_at: new Date().toISOString(),
  })

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }

  // Log the action
  await supabase.from('admin_logs').insert({
    admin_email: user.email,
    action,
    target_email,
  })

  return NextResponse.json({
    success: true,
    action,
    target_email,
    is_admin,
  })
}

export async function GET(req: NextRequest) {
  const supabase = createSupabaseClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user?.email) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
  }

  // Check if requester is admin
  const { data: adminCheck } = await supabase
    .from('users')
    .select('is_admin')
    .eq('email', user.email)
    .single()

  if (!adminCheck?.is_admin) {
    return NextResponse.json({ error: 'admin access required' }, { status: 403 })
  }

  // Return all users
  const { data: users, error } = await supabase
    .from('users')
    .select('email, is_admin, created_at')
    .order('created_at', { ascending: false })

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }

  return NextResponse.json({ users })
}
