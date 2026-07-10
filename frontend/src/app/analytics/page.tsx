// frontend/src/app/analytics/page.tsx
'use client'
import { useEffect, useState } from 'react'
import { PageLayout } from '@/components/PageLayout'
import { StatsBar }   from '@/components/StatsBar'
import { api }        from '@/lib/api'
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
  PieChart, Pie, Cell
} from 'recharts'
import { format, subDays } from 'date-fns'

const SEVERITY_COLOURS = {
  'Life-threatening': '#DC2626',
  'Severe':           '#EA580C',
  'Moderate':         '#CA8A04',
  'Mild':             '#16A34A',
}

const CHANNEL_COLOURS = [
  '#F5C518','#8BC34A','#9B8EC4','#0EA5E9','#F97316'
]

export default function AnalyticsPage() {
const [raw, setRaw]     = useState<any[]>([])
const [loading, setLoading] = useState(true)

useEffect(() => {
  api.analytics()
    .then(r => setRaw(r.data || []))
    .catch(console.error)
    .finally(() => setLoading(false))
}, [])

// ── Build severity trend (last 7 days) ───────────────
const trendData = Array.from({ length: 7 }, (_, i) => {
  const d = subDays(new Date(), 6 - i)
  const ds = format(d, 'yyyy-MM-dd')
  const dayEvents = raw.filter(e =>
    e.created_at?.startsWith(ds)
  )
  return {
    date: format(d, 'dd MMM'),
    Mild: dayEvents.filter(e => e.severity === 'Mild').length,
    Moderate: dayEvents.filter(e => e.severity === 'Moderate').length,
    Severe: dayEvents.filter(e => e.severity === 'Severe').length,
    'Life-threatening': dayEvents.filter(
      e => e.severity === 'Life-threatening'
    ).length,
  }
})

// ── Build channel distribution ────────────────────────
const channelCounts: Record<string, number> = {}
raw.forEach(e => {
  channelCounts[e.channel] = (channelCounts[e.channel] || 0) + 1
})
const channelData = Object.entries(channelCounts).map(
  ([name, value]) => ({ name, value })
)

// ── Build category breakdown ──────────────────────────
const catCounts: Record<string, number> = {}
raw.forEach(e => {
  catCounts[e.category] = (catCounts[e.category] || 0) + 1
})
const catData = Object.entries(catCounts).map(
    ([name, count]) => ({ name, count })
)

if (loading) {
  return (
    <PageLayout title="Analytics">
      <div className="text-center py-20 text-gray-400">Loading...</div>
    </PageLayout>
  )
}

return (
  <PageLayout
    title="Analytics"
    subtitle="Adverse event trends, channel distribution, and compliance metrics"
  >
    <StatsBar />

     <div className="grid grid-cols-1 gap-6">

       {/* Severity trend */}
       <div className="bg-white rounded-xl border border-gray-100
                       shadow-sm p-6">
         <h3 className="font-semibold text-gray-900 mb-4">
           Events by Severity — Last 7 Days
         </h3>
         <ResponsiveContainer width="100%" height={280}>
           <LineChart data={trendData}>
             <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
             <XAxis dataKey="date" tick={{ fontSize: 12 }} />
             <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
             <Tooltip />
             <Legend />
             {Object.entries(SEVERITY_COLOURS).map(([s, c]) => (
               <Line
                 key={s}
                 type="monotone"
                 dataKey={s}
                 stroke={c}
                 strokeWidth={2}
                 dot={{ r: 4 }}
               />
             ))}
    </LineChart>
  </ResponsiveContainer>
</div>

<div className="grid grid-cols-2 gap-6">
  {/* Channel distribution */}
  <div className="bg-white rounded-xl border border-gray-100
                   shadow-sm p-6">
    <h3 className="font-semibold text-gray-900 mb-4">
      Events by Channel
    </h3>
    {channelData.length === 0 ? (
      <p className="text-gray-400 text-sm py-8 text-center">
        No data yet
      </p>
    ) : (
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie
            data={channelData}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy="50%"
            outerRadius={80}
            label={({ name, value }) => `${name}: ${value}`}
            labelLine={false}
          >
            {channelData.map((_, i) => (
               <Cell
                 key={i}
                 fill={CHANNEL_COLOURS[i % CHANNEL_COLOURS.length]}
               />
            ))}
          </Pie>
          <Tooltip />
        </PieChart>
      </ResponsiveContainer>
    )}
  </div>

  {/* Category breakdown */}
  <div className="bg-white rounded-xl border border-gray-100
                             shadow-sm p-6">
               <h3 className="font-semibold text-gray-900 mb-4">
                 Events by Category
               </h3>
               {catData.length === 0 ? (
                 <p className="text-gray-400 text-sm py-8 text-center">
                   No data yet
                 </p>
               ) : (
                 <ResponsiveContainer width="100%" height={220}>
                   <BarChart data={catData} layout="vertical">
                     <CartesianGrid
                       strokeDasharray="3 3"
                       stroke="#F1F5F9"
                       horizontal={false}
                     />
                     <XAxis type="number"
                       tick={{ fontSize: 11 }}
                       allowDecimals={false}
                     />
                     <YAxis
                       type="category"
                       dataKey="name"
                       tick={{ fontSize: 11 }}
                       width={120}
                     />
                     <Tooltip />
                     <Bar dataKey="count" fill="#9B8EC4" radius={[0,4,4,0]} />
                   </BarChart>
                 </ResponsiveContainer>
               )}
             </div>
           </div>

          </div>
        </PageLayout>
    )
}
