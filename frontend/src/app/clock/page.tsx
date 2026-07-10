// frontend/src/app/clock/page.tsx
'use client'
import { useEffect, useState } from 'react'
import { PageLayout }    from '@/components/PageLayout'
import { SeverityBadge } from '@/components/SeverityBadge'
import { AdverseEvent } from '@/lib/types'
import { api }           from '@/lib/api'
import { deadlineStatus, formatDate, channelIcon } from '@/lib/utils'
import { Clock, AlertOctagon } from 'lucide-react'

export default function ClockPage() {
  const [events, setEvents] = useState<AdverseEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)

    useEffect(() => {
      api.clock()
        .then(r => setEvents(r.data || []))
        .catch(console.error)
        .finally(() => setLoading(false))

        // Reload every 5 minutes
 const dataI = setInterval(() => {
   api.clock().then(r => setEvents(r.data || [])).catch(console.error)
 }, 300_000)

 // Tick every minute to update countdowns
 const tickI = setInterval(() => setTick(t => t + 1), 60_000)

  return () => { clearInterval(dataI); clearInterval(tickI) }
}, [])

const sorted = [...events].sort((a, b) => {
  if (!a.regulatory_deadline) return 1
  if (!b.regulatory_deadline) return -1
  return new Date(a.regulatory_deadline).getTime() -
         new Date(b.regulatory_deadline).getTime()
})

return (
  <PageLayout
    title="Compliance Clock"
    subtitle="Regulatory reporting deadlines — live countdown"
  >
    {loading ? (
      <div className="text-center py-20 text-gray-400">Loading...</div>
    ) : sorted.length === 0 ? (
      <div className="text-center py-20 text-gray-400">
        <Clock size={48} className="mx-auto mb-3 opacity-30" />
        <p>No open deadlines. All reports are up to date.</p>
      </div>
    ) : (
      <div className="space-y-3 max-w-4xl">
        {sorted.map(ae => {
          const ds = ae.regulatory_deadline
            ? deadlineStatus(ae.regulatory_deadline)
            : null
          const isOverdue = ds?.label === 'OVERDUE'

         return (
           <div
             key={ae.id}
             className={`bg-white rounded-xl border shadow-sm p-5
               ${isOverdue
                 ? 'border-red-300 bg-red-50'
        : 'border-gray-100'}`}
>
    <div className="flex items-center justify-between gap-4">
      <div className="flex items-center gap-3 min-w-0">
        {isOverdue && (
           <AlertOctagon
             size={20}
             className="text-red-500 shrink-0"
           />
        )}
        <span className="text-lg shrink-0">
           {channelIcon(ae.channel)}
        </span>
        <div className="min-w-0">
           <div className="flex items-center gap-2 flex-wrap">
             <span className="font-semibold text-sm">
               {ae.patients?.patient_code}
             </span>
             <span className="text-xs text-gray-400">
               {ae.patients?.full_name}
             </span>
             <SeverityBadge severity={ae.severity} />
           </div>
           <p className="text-xs text-gray-500 mt-0.5">
             {ae.trials?.regulatory_body} —{' '}
             Drug: {ae.trials?.drug_name}
             {ae.is_backdated && (
               <span className="ml-2 text-red-500 font-medium">
                 ⚠️ Backdated ({ae.backdated_gap_days}d ago)
               </span>
             )}
           </p>
        </div>
      </div>

      <div className="shrink-0 text-right">
        {ds ? (
          <div className={`px-4 py-2 rounded-lg ${ds.bg}`}>
            <p className={`text-2xl font-bold ${ds.colour}`}>
              {ds.label}
            </p>
            <p className="text-xs text-gray-500">
              {ae.regulatory_deadline
                                ? formatDate(ae.regulatory_deadline)
                                : ''}
                            </p>
                          </div>
                       ) : (
                          <span className="text-gray-400 text-sm">
                            No deadline set
                          </span>
                       )}
                     </div>
                   </div>
                 </div>
                )
              })}
            </div>
          )}
        </PageLayout>
    )
}
