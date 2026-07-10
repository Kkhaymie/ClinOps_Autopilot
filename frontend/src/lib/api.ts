// frontend/src/lib/api.ts
import { supabase } from './supabase'

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function req(path: string, options: RequestInit = {}) {
  const { data: { session } } = await supabase.auth.getSession()

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(session ? { Authorization: `Bearer ${session.access_token}` } : {}),
      ...options.headers,
    },
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export const api = {
  stats:    () => req('/api/stats'),
  pending:  () => req('/api/pending-approvals'),
  // approver identity now comes from the auth token server-side, not a
  // string the client hands over
  approve:  (id: string, notes?: string) =>
    req(`/api/approve/${id}${notes ? `?notes=${encodeURIComponent(notes)}` : ''}`,
      { method: 'POST' }),
  reject:   (id: string, reason?: string) =>
    req(`/api/reject/${id}${reason ? `?reason=${encodeURIComponent(reason)}` : ''}`,
      { method: 'POST' }),
  clock:     () => req('/api/compliance-clock'),
  signals:   () => req('/api/safety-signals'),
  analytics: () => req('/api/analytics/events'),
  tmf: (filters?: Record<string, string>) => {
    const qs = filters
      ? '?' + new URLSearchParams(filters).toString()
      : ''
    return req(`/api/trial-master-file${qs}`)
  },
  escalationRules: (trialId?: string) =>
    req(`/api/escalation-rules${trialId ? `?trial_id=${trialId}` : ''}`),
  createEscalationRule: (rule: Record<string, unknown>) =>
    req('/api/escalation-rules', { method: 'POST', body: JSON.stringify(rule) }),

  // staff management, admin only
  listStaff: () => req('/api/staff'),
  listTrialsForStaff: () => req('/api/staff/trials'),
  createStaff: (payload: Record<string, unknown>) =>
    req('/api/staff', { method: 'POST', body: JSON.stringify(payload) }),
  deactivateStaff: (id: string) => req(`/api/staff/${id}/deactivate`, { method: 'POST' }),
  reactivateStaff: (id: string) => req(`/api/staff/${id}/reactivate`, { method: 'POST' }),
  assignTrial: (staffId: string, trialId: string) =>
    req(`/api/staff/${staffId}/trials/${trialId}`, { method: 'POST' }),
  unassignTrial: (staffId: string, trialId: string) =>
    req(`/api/staff/${staffId}/trials/${trialId}`, { method: 'DELETE' }),
}