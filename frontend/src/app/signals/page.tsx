// frontend/src/app/signals/page.tsx
'use client'
import { useEffect, useState } from 'react'
import { PageLayout }    from '@/components/PageLayout'
import { SafetySignal } from '@/lib/types'
import { api }           from '@/lib/api'
import { formatDate }    from '@/lib/utils'
import {
  AlertTriangle, Users, Pill
} from 'lucide-react'

export default function SignalsPage() {
  const [signals, setSignals] = useState<SafetySignal[]>([])
  const [loading, setLoading] = useState(true)

    useEffect(() => {
      api.signals()
    .then(r => setSignals(r.data || []))
    .catch(console.error)
    .finally(() => setLoading(false))
}, [])

return (
  <PageLayout
    title="Safety Signals"
    subtitle="Cross-patient adverse event pattern detection"
  >
    {loading ? (
      <div className="text-center py-20 text-gray-400">Loading...</div>
    ) : signals.length === 0 ? (
      <div className="text-center py-20 text-gray-400">
        <AlertTriangle size={48} className="mx-auto mb-3 opacity-30" />
        <p>No open safety signals detected.</p>
      </div>
    ) : (
      <div className="space-y-4 max-w-3xl">
        {signals.map(sig => (
          <div
            key={sig.id}
            className="bg-white rounded-xl border border-orange-200
                       border-l-4 border-l-orange-500 shadow-sm p-5"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <AlertTriangle
                  size={22}
                  className="text-orange-500 mt-0.5 shrink-0"
                />
                <div>
                  <p className="font-semibold text-gray-900">
                    Safety Signal — {sig.signal_type.replace(/_/g,' ')}
                  </p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Detected {formatDate(sig.detection_time)}
                  </p>
                </div>
              </div>
              <span className="text-xs bg-orange-100 text-orange-700
                               px-2.5 py-1 rounded-full font-medium
                               shrink-0">
    {sig.status}
  </span>
</div>

<div className="mt-4 grid grid-cols-3 gap-3">
  <div className="bg-gray-50 rounded-lg p-3 text-center">
    <Users size={18} className="mx-auto text-gray-400 mb-1" />
    <p className="text-2xl font-bold text-gray-900">
      {sig.affected_patient_count}
    </p>
    <p className="text-xs text-gray-500">Patients affected</p>
  </div>
  <div className="bg-gray-50 rounded-lg p-3">
    <p className="text-[10px] uppercase text-gray-400
                  font-medium mb-1">
      Common symptoms
    </p>
    <div className="flex flex-wrap gap-1">
      {sig.common_symptoms.map(s => (
        <span key={s}
          className="text-xs bg-blue-50 text-blue-700
                     px-2 py-0.5 rounded-full">
          {s}
        </span>
      ))}
    </div>
  </div>
  <div className="bg-gray-50 rounded-lg p-3">
    <Pill size={16} className="text-gray-400 mb-1" />
    <p className="text-[10px] uppercase text-gray-400
                  font-medium">
      Drug batch
    </p>
    <p className="text-sm font-semibold text-gray-700">
      {sig.drug_batch || 'Multiple / Unknown'}
    </p>
  </div>
</div>

<div className="mt-4 bg-orange-50 border border-orange-100
                rounded-lg px-4 py-3 text-sm text-orange-900
                leading-relaxed">
  <span className="font-semibold">Recommendation: </span>
                    {sig.recommendation}
                  </div>
                </div>
              ))}
            </div>
          )}
        </PageLayout>
    )
}
