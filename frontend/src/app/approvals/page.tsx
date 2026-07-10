// frontend/src/app/approvals/page.tsx
'use client'
import { useEffect, useState, useCallback } from 'react'
import { PageLayout }    from '@/components/PageLayout'
import { ApprovalCard } from '@/components/ApprovalCard'
import { AdverseEvent } from '@/lib/types'
import { api }           from '@/lib/api'
import { CheckSquare }   from 'lucide-react'

export default function ApprovalsPage() {
  const [events, setEvents] = useState<AdverseEvent[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await api.pending()
      setEvents(data || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  return (
    <PageLayout
      title="Pending Approvals"
      subtitle={`${events.length} report${events.length !== 1 ? 's' : ''} awaiting review`}
    >
      {loading ? (
        <div className="text-center py-20 text-gray-400">Loading...</div>
      ) : events.length === 0 ? (
        <div className="text-center py-20 text-gray-400">
          <CheckSquare size={48} className="mx-auto mb-3 opacity-30" />
          <p className="font-medium">All caught up!</p>
          <p className="text-sm mt-1">No reports waiting for approval.</p>
        </div>
          ) : (
            <div className="space-y-5 max-w-3xl">
              {events.map(ae => (
                <ApprovalCard
                  key={ae.id}
                  ae={ae}
                  onAction={load}
                />
              ))}
            </div>
          )}
        </PageLayout>
    )
}
