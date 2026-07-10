// frontend/src/app/page.tsx
'use client'
import { useEffect, useState, useCallback } from 'react'
import { PageLayout }    from '@/components/PageLayout'
import { StatsBar }      from '@/components/StatsBar'
import { SeverityBadge } from '@/components/SeverityBadge'
import { AdverseEvent } from '@/lib/types'
import {
  channelIcon, channelLabel,
  timeAgo, severityBorder
} from '@/lib/utils'
import { supabase } from '@/lib/supabase'
import { api }       from '@/lib/api'
import Link from 'next/link'
import {
  AlertTriangle, Wifi, RefreshCw
} from 'lucide-react'

export default function InboxPage() {
  const [events, setEvents] = useState<AdverseEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter]   = useState<string>('ALL')

  const load = useCallback(async () => {
    try {
      const { data } = await api.tmf()
      setEvents(data || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()

    // Real-time updates via Supabase
    const channel = supabase
      .channel('ae-realtime')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'adverse_events' },
        () => load()
      )
      .subscribe()

    return () => { supabase.removeChannel(channel) }
  }, [load])
const severities = ['ALL','Life-threatening','Severe','Moderate','Mild']

const filtered = filter === 'ALL'
  ? events
  : events.filter(e => e.severity === filter)

return (
  <PageLayout
    title="Live Inbox"
    subtitle="All incoming patient messages — all channels, all languages"
  >
    <StatsBar />

   {/* Filter tabs */}
   <div className="flex gap-2 mb-5 flex-wrap">
     {severities.map(s => (
       <button
         key={s}
         onClick={() => setFilter(s)}
         className={`px-3 py-1.5 rounded-full text-sm font-medium
                     transition-colors ${
           filter === s
             ? 'bg-[#0A0F2C] text-white'
             : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
         }`}
       >
         {s}
         <span className="ml-1.5 text-xs opacity-60">
           {s === 'ALL'
             ? events.length
             : events.filter(e => e.severity === s).length}
         </span>
       </button>
     ))}
     <button
       onClick={load}
       className="ml-auto px-3 py-1.5 rounded-full text-sm
                  bg-white border border-gray-200 text-gray-600
                  hover:bg-gray-50 flex items-center gap-1.5"
     >
       <RefreshCw size={13} />
       Refresh
     </button>
</div>

{/* Events list */}
{loading ? (
  <div className="text-center py-20 text-gray-400">
    Loading...
  </div>
) : filtered.length === 0 ? (
  <div className="text-center py-20 text-gray-400">
    <Wifi size={40} className="mx-auto mb-3 opacity-30" />
    <p>No events yet. Waiting for patient messages...</p>
  </div>
) : (
  <div className="space-y-3">
    {filtered.map(ae => (
      <Link key={ae.id} href={`/approvals?id=${ae.id}`}>
        <div className={`bg-white rounded-xl border border-gray-100
                         border-l-4 ${severityBorder(ae.severity)}
                         shadow-sm px-5 py-4 hover:shadow-md
                         transition-shadow cursor-pointer`}>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 flex-wrap min-w-0">
              <span className="text-xl shrink-0">
                {channelIcon(ae.channel)}
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-sm text-gray-900">
                    {ae.patients?.patient_code ?? 'Unknown'}
                  </span>
                  <span className="text-xs text-gray-400">
                    {ae.patients?.full_name}
                  </span>
                  <span className="text-xs text-gray-400">
                    via {channelLabel(ae.channel)}
                  </span>
                  {ae.language_detected !== 'English' && (
                    <span className="text-[10px] bg-indigo-50
                                    text-indigo-700 px-2 py-0.5
                                    rounded-full">
                      {ae.language_detected}
                    </span>
                  )}
                           </div>
                           <p className="text-sm text-gray-500 mt-0.5 truncate">
                             "{ae.original_message}"
                           </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        {ae.trad_medicine_flag && (
                           <span title="Traditional medicine detected">
                             <AlertTriangle
                               size={16}
                               className="text-orange-500"
                             />
                           </span>
                        )}
                        <SeverityBadge severity={ae.severity} />
                        <span className="text-xs text-gray-400 whitespace-nowrap">
                           {timeAgo(ae.created_at)}
                        </span>
                        <span className={`text-xs px-2 py-0.5 rounded-full
                          font-medium ${
                             ae.status === 'PENDING_APPROVAL'
                               ? 'bg-yellow-100 text-yellow-700'
                               : ae.status === 'APPROVED'
                               ? 'bg-green-100 text-green-700'
                               : 'bg-gray-100 text-gray-500'
                           }`}>
                           {ae.status.replace('_', ' ')}
                        </span>
                      </div>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </PageLayout>
    )
}
