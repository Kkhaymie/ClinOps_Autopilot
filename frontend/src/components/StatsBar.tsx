// frontend/src/components/StatsBar.tsx
'use client'
import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { DashboardStats } from '@/lib/types'
import {
  FileText, Clock, AlertTriangle, Activity
} from 'lucide-react'

export function StatsBar() {
  const [stats, setStats] = useState<DashboardStats | null>(null)

  useEffect(() => {
    api.stats().then(setStats).catch(console.error)
    const i = setInterval(() => {
      api.stats().then(setStats).catch(console.error)
    }, 30_000)
    return () => clearInterval(i)
  }, [])

  const cards = [
    {
      label: 'Pending Approval',
      value: stats?.pending_approvals ?? '—',
      icon: Clock,
      colour: 'text-yellow-600',
      bg: 'bg-yellow-50',
    },
    {
      label: 'Total AEs',
      value: stats?.total_aes ?? '—',
      icon: FileText,
      colour: 'text-blue-600',
      bg: 'bg-blue-50',
    },
    {
      label: 'Severe Events',
      value: stats?.severe_events ?? '—',
      icon: Activity,
          colour: 'text-red-600',
          bg: 'bg-red-50',
        },
        {
          label: 'Open Signals',
          value: stats?.open_signals ?? '—',
          icon: AlertTriangle,
          colour: 'text-orange-600',
          bg: 'bg-orange-50',
        },
    ]

    return (
      <div className="grid grid-cols-4 gap-4 mb-6">
        {cards.map(({ label, value, icon: Icon, colour, bg }) => (
          <div
            key={label}
            className="bg-white rounded-xl border border-gray-100
                        px-5 py-4 flex items-center gap-4 shadow-sm"
          >
            <div className={`${bg} p-3 rounded-lg`}>
               <Icon size={20} className={colour} />
            </div>
            <div>
               <p className="text-2xl font-bold text-gray-900">{value}</p>
               <p className="text-xs text-gray-500">{label}</p>
            </div>
          </div>
        ))}
      </div>
    )
}
