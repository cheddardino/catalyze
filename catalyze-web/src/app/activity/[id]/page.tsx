import { notFound } from 'next/navigation'
import Link from 'next/link'
import { createClient } from '@/lib/supabase-server'
import { displayKind } from '@/lib/supabase'
import { ConsistencyBadge } from '@/components/ConsistencyBadge'
import { SeverityBadge } from '@/components/SeverityBadge'
import { ColorBar } from '@/components/ColorBar'
import { DetectionImage } from '@/components/DetectionImage'

export default async function DetectionDetailPage({ params }: { params: { id: string } }) {
  const id = parseInt(params.id, 10)
  if (isNaN(id)) notFound()

  const supabase = createClient()
  const { data: d } = await supabase
    .from('detections')
    .select('id, local_id, timestamp, kind, bbox_json, red_pct, yellow_pct, green_pct, brown_pct, remark, severity, model_version, image_cat, image_poop, image_full, image_crop, image_overlay, created_at')
    .eq('id', id)
    .single()

  if (!d) notFound()

  const ts = new Date(d.timestamp).toLocaleString('en-PH', {
    weekday: 'short', month: 'short', day: 'numeric',
    year: 'numeric', hour: 'numeric', minute: '2-digit',
    timeZone: 'Asia/Manila',
  })

  return (
    <div className="space-y-5">
      <Link href="/activity" className="text-sm text-brand-600 font-medium hover:underline">← Back to Activity</Link>

      {/* Two-phase images */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <p className="text-xs text-gray-500 font-medium text-center">Cat (entering)</p>
          <DetectionImage
            src={(d as Record<string, unknown>).image_cat as string | null ?? null}
            alt="Cat entering litterbox"
            className="aspect-square w-full"
            emptyLabel="No cat photo"
          />
        </div>
        <div className="space-y-1">
          <p className="text-xs text-gray-500 font-medium text-center">Poop (after exit)</p>
          <DetectionImage
            src={(d as Record<string, unknown>).image_poop as string | null ?? d.image_crop ?? null}
            alt="Poop after cat exit"
            className="aspect-square w-full"
            emptyLabel="No poop photo"
          />
        </div>
      </div>

      {/* Header */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-2">
        <div className="flex items-center gap-2 flex-wrap">
          <ConsistencyBadge kind={d.kind} />
          <SeverityBadge severity={d.severity} />
        </div>
        {d.remark && <p className="text-gray-700 text-sm leading-relaxed">{d.remark}</p>}
        <p className="text-xs text-gray-400">{ts}</p>
      </div>

      {/* Color breakdown — only show colors with a value > 0 */}
      {(() => {
        const bars = [
          { label: 'Red',    pct: d.red_pct,    color: 'red'    },
          { label: 'Yellow', pct: d.yellow_pct, color: 'yellow' },
          { label: 'Green',  pct: d.green_pct,  color: 'green'  },
          { label: 'Brown',  pct: d.brown_pct,  color: 'brown'  },
        ].filter(b => (b.pct ?? 0) > 0)

        if (bars.length === 0) return null

        return (
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-400 text-center">Color breakdown</h2>
            {bars.map(b => (
              <ColorBar key={b.label} label={b.label} pct={b.pct} color={b.color} />
            ))}
          </div>
        )
      })()}

      {/* Color analysis overlay */}
      {d.image_overlay && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-400 text-center">Color analysis overlay</h2>
          <DetectionImage
            src={d.image_overlay as string}
            alt="Color analysis overlay"
            className="w-full rounded-lg"
            emptyLabel="No overlay"
          />
          <p className="text-xs text-gray-500 text-center">Detection #{d.id}</p>
        </div>
      )}

      {/* Info */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2 text-center">Info</h2>
        <dl className="text-sm space-y-1">
          <div className="flex gap-2">
            <dt className="text-gray-500 w-28">Detection ID</dt>
            <dd className="text-gray-800">#{d.id}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="text-gray-500 w-28">Consistency</dt>
            <dd className="text-gray-800">{displayKind(d.kind)}</dd>
          </div>
          {d.model_version && (
            <div className="flex gap-2">
              <dt className="text-gray-500 w-28">Model</dt>
              <dd className="text-gray-800">{d.model_version}</dd>
            </div>
          )}
        </dl>
      </div>
    </div>
  )
}
