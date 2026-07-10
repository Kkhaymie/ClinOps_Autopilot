// frontend/src/app/tmf/page.tsx
'use client'
import { useEffect, useState } from 'react'
import { PageLayout }    from '@/components/PageLayout'
import { SeverityBadge } from '@/components/SeverityBadge'
import { AdverseEvent } from '@/lib/types'
import { api }           from '@/lib/api'
import {
  channelIcon, channelLabel, formatDate
} from '@/lib/utils'
import { Search, Filter } from 'lucide-react'

export default function TMFPage() {
  const [events, setEvents]   = useState<AdverseEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch]   = useState('')
  const [sevFilter, setSev]   = useState('')
  const [chanFilter, setChan] = useState('')
  const [statFilter, setStat] = useState('')

    useEffect(() => {
      const filters: Record<string,string> = {}
      if (sevFilter) filters.severity = sevFilter
      if (chanFilter) filters.channel = chanFilter
      if (statFilter) filters.status   = statFilter

        api.tmf(Object.keys(filters).length ? filters : undefined)
    .then(r => setEvents(r.data || []))
    .catch(console.error)
    .finally(() => setLoading(false))
}, [sevFilter, chanFilter, statFilter])

const filtered = events.filter(e => {
  if (!search) return true
  const q = search.toLowerCase()
  return (
    e.patients?.patient_code?.toLowerCase().includes(q) ||
    e.patients?.full_name?.toLowerCase().includes(q) ||
    e.original_message?.toLowerCase().includes(q) ||
    e.language_detected?.toLowerCase().includes(q)
  )
})

return (
  <PageLayout
    title="Trial Master File"
    subtitle="Complete searchable record of all adverse events"
  >
    {/* Filters */}
    <div className="flex gap-3 mb-5 flex-wrap">
      <div className="flex items-center gap-2 bg-white border
                      border-gray-200 rounded-lg px-3 py-2 flex-1
                      min-w-48">
        <Search size={15} className="text-gray-400" />
        <input
          type="text"
          placeholder="Search patient, message, language..."
          className="flex-1 text-sm outline-none bg-transparent"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

     <select
       className="bg-white border border-gray-200 rounded-lg
                  px-3 py-2 text-sm text-gray-600 outline-none"
       value={sevFilter}
       onChange={e => setSev(e.target.value)}
     >
       <option value="">All Severities</option>
   {['Mild','Moderate','Severe','Life-threatening'].map(s => (
     <option key={s} value={s}>{s}</option>
   ))}
 </select>

 <select
   className="bg-white border border-gray-200 rounded-lg
              px-3 py-2 text-sm text-gray-600 outline-none"
   value={chanFilter}
   onChange={e => setChan(e.target.value)}
 >
   <option value="">All Channels</option>
   {['whatsapp','sms','telegram','email','physical_mail'].map(c => (
     <option key={c} value={c}>{channelLabel(c as never)}</option>
   ))}
 </select>

  <select
    className="bg-white border border-gray-200 rounded-lg
               px-3 py-2 text-sm text-gray-600 outline-none"
    value={statFilter}
    onChange={e => setStat(e.target.value)}
  >
    <option value="">All Statuses</option>
    {['PENDING_APPROVAL','APPROVED','REJECTED'].map(s => (
      <option key={s} value={s}>{s.replace('_',' ')}</option>
    ))}
  </select>
</div>

{/* Table */}
<div className="bg-white rounded-xl border border-gray-100
                shadow-sm overflow-hidden">
  <div className="overflow-x-auto">
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-gray-100 bg-gray-50">
          {['Patient','Channel','Symptoms','Severity',
            'Language','Status','Trad. Med.','Date'
          ].map(h => (
            <th key={h}
              className="text-left px-4 py-3 text-xs font-semibold
                         text-gray-500 uppercase tracking-wide
                  whitespace-nowrap">
        {h}
      </th>
    ))}
  </tr>
</thead>
<tbody className="divide-y divide-gray-50">
  {loading ? (
    <tr>
      <td colSpan={8}
        className="text-center py-12 text-gray-400">
        Loading...
      </td>
    </tr>
  ) : filtered.length === 0 ? (
    <tr>
      <td colSpan={8}
        className="text-center py-12 text-gray-400">
        No records found.
      </td>
    </tr>
  ) : filtered.map(ae => (
    <tr key={ae.id}
      className="hover:bg-gray-50 transition-colors">
      <td className="px-4 py-3 whitespace-nowrap">
        <p className="font-medium text-gray-900">
          {ae.patients?.patient_code}
        </p>
        <p className="text-xs text-gray-400">
          {ae.patients?.full_name}
        </p>
      </td>
      <td className="px-4 py-3 whitespace-nowrap">
        <span className="flex items-center gap-1.5 text-gray-600">
          {channelIcon(ae.channel)}
          {channelLabel(ae.channel)}
        </span>
      </td>
      <td className="px-4 py-3 max-w-[200px]">
        <div className="flex flex-wrap gap-1">
          {ae.symptoms.slice(0,3).map(s => (
            <span key={s}
              className="text-xs bg-blue-50 text-blue-700
                        px-1.5 py-0.5 rounded">
              {s}
            </span>
          ))}
          {ae.symptoms.length > 3 && (
            <span className="text-xs text-gray-400">
              +{ae.symptoms.length - 3}
            </span>
          )}
        </div>
      </td>
      <td className="px-4 py-3 whitespace-nowrap">
        <SeverityBadge severity={ae.severity} />
      </td>
      <td className="px-4 py-3 whitespace-nowrap">
        <span className="text-xs text-gray-600">
          {ae.language_detected}
        </span>
      </td>
      <td className="px-4 py-3 whitespace-nowrap">
        <span className={`text-xs font-medium px-2 py-0.5
          rounded-full ${
            ae.status === 'PENDING_APPROVAL'
              ? 'bg-yellow-100 text-yellow-700'
              : ae.status === 'APPROVED'
              ? 'bg-green-100 text-green-700'
              : 'bg-gray-100 text-gray-500'
          }`}>
          {ae.status.replace('_', ' ')}
        </span>
      </td>
      <td className="px-4 py-3 text-center">
        {ae.trad_medicine_flag
          ? <span title={ae.trad_medicine_type || ''}>⚠️</span>
          : <span className="text-gray-300">—</span>}
      </td>
      <td className="px-4 py-3 whitespace-nowrap text-xs
                     text-gray-400">
        {formatDate(ae.created_at)}
      </td>
    </tr>
  ))}
</tbody>
              </table>
            </div>
            <div className="px-4 py-3 border-t border-gray-50 text-xs
                            text-gray-400">
              Showing {filtered.length} of {events.length} records
            </div>
          </div>
        </PageLayout>
    )
}
