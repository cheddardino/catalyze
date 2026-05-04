import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'
import { NextRequest, NextResponse } from 'next/server'

type MotorAction = 'clean' | 'cw' | 'ccw' | 'full_cycle'

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

  let body: { action?: MotorAction }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'invalid json' }, { status: 400 })
  }

  if (!body.action || !['clean', 'cw', 'ccw', 'full_cycle'].includes(body.action)) {
    return NextResponse.json({ error: 'unsupported action' }, { status: 400 })
  }

  // Only admins can trigger 'clean' action
  if (body.action === 'clean') {
    const { data: userRecord } = await supabase
      .from('users')
      .select('is_admin')
      .eq('email', user.email)
      .single()

    if (!userRecord?.is_admin) {
      return NextResponse.json(
        { error: 'admin access required for clean action' },
        { status: 403 }
      )
    }
  }

  const { data, error } = await supabase
    .from('commands')
    .insert({
      type: body.action,
      status: 'pending',
      triggered_by: user.email,
    })
    .select('id')
    .single()

  if (error || !data) {
    return NextResponse.json(
      { error: error?.message ?? 'failed to enqueue command' },
      { status: 500 }
    )
  }

  return NextResponse.json({ id: data.id, status: 'pending' }, { status: 201 })
}