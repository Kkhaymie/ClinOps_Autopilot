// frontend/src/app/staff/page.tsx
'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { PageLayout } from '@/components/PageLayout'
import { useAuth } from '@/lib/auth-context'
import { api } from '@/lib/api'
import { UserPlus, ShieldOff, ShieldCheck } from 'lucide-react'

interface Trial {
  id: string
  trial_name: string
  drug_name: string
}

interface StaffRow {
  id: string
  full_name: string
  email: string
  role: string
  phone?: string
  active: boolean
  staff_trials?: { trial_id: string }[]
}

const ROLES = ['admin', 'coordinator', 'pi', 'sponsor', 'site_staff']

export default function StaffPage() {
  const { staff } = useAuth()
  const router = useRouter()
  const [rows, setRows] = useState<StaffRow[]>([])
  const [trials, setTrials] = useState<Trial[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [form, setForm] = useState({
    email: '', password: '', full_name: '', role: 'coordinator',
    phone: '', trial_ids: [] as string[],
  })

  useEffect(() => {
    if (staff && staff.role !== 'admin') {
      router.replace('/')
    }
  }, [staff, router])

  async function load() {
    setLoading(true)
    try {
      const [staffRes, trialsRes] = await Promise.all([
        api.listStaff(),
        api.listTrialsForStaff(),
      ])
      setRows(staffRes.data || [])
      setTrials(trialsRes.data || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const res = await api.createStaff(form)
      if (!res.success) {
        setError(res.error || 'Failed to create staff member')
        return
      }
      setShowForm(false)
      setForm({ email: '', password: '', full_name: '', role: 'coordinator', phone: '', trial_ids: [] })
      await load()
    } catch {
      setError('Failed to create staff member')
    } finally {
      setSaving(false)
    }
  }

  async function toggleActive(row: StaffRow) {
    if (row.active) {
      await api.deactivateStaff(row.id)
    } else {
      await api.reactivateStaff(row.id)
    }
    await load()
  }

  function toggleTrial(trialId: string) {
    setForm(f => ({
      ...f,
      trial_ids: f.trial_ids.includes(trialId)
        ? f.trial_ids.filter(id => id !== trialId)
        : [...f.trial_ids, trialId],
    }))
  }

  const needsTrials = ['pi', 'sponsor', 'site_staff'].includes(form.role)

  return (
    <PageLayout title="Staff" subtitle="Manage coordinator, PI, sponsor, and site staff accounts">
      <div className="mb-4 flex justify-end">
        <button
          onClick={() => setShowForm(s => !s)}
          className="flex items-center gap-2 bg-[#0A0F2C] text-white text-sm font-medium rounded-lg px-4 py-2"
        >
          <UserPlus size={16} />
          New staff member
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="mb-6 bg-white border border-gray-200 rounded-xl p-6 space-y-4 max-w-xl">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Full name</label>
              <input required value={form.full_name}
                onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Role</label>
              <select value={form.role}
                onChange={e => setForm(f => ({ ...f, role: e.target.value, trial_ids: [] }))}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm capitalize">
                {ROLES.map(r => <option key={r} value={r}>{r.replace('_', ' ')}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Email</label>
              <input required type="email" value={form.email}
                onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Temporary password</label>
              <input required type="password" minLength={8} value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Phone (WhatsApp/SMS)</label>
              <input value={form.phone}
                onChange={e => setForm(f => ({ ...f, phone: e.target.value }))}
                placeholder="+234..."
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            </div>
          </div>

          {needsTrials && (
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-2">Assigned trials</label>
              <div className="space-y-1 max-h-32 overflow-y-auto border border-gray-200 rounded-lg p-2">
                {trials.map(t => (
                  <label key={t.id} className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={form.trial_ids.includes(t.id)}
                      onChange={() => toggleTrial(t.id)} />
                    {t.trial_name} ({t.drug_name})
                  </label>
                ))}
                {trials.length === 0 && (
                  <p className="text-xs text-gray-400">No trials found.</p>
                )}
              </div>
            </div>
          )}

          {error && <p className="text-sm text-red-600">{error}</p>}

          <div className="flex gap-2">
            <button type="submit" disabled={saving}
              className="bg-[#0A0F2C] text-white text-sm font-medium rounded-lg px-4 py-2 disabled:opacity-50">
              {saving ? 'Creating...' : 'Create account'}
            </button>
            <button type="button" onClick={() => setShowForm(false)}
              className="text-sm text-gray-500 px-4 py-2">
              Cancel
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <div className="text-center py-20 text-gray-400">Loading...</div>
      ) : (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="text-left px-4 py-3">Name</th>
                <th className="text-left px-4 py-3">Email</th>
                <th className="text-left px-4 py-3">Role</th>
                <th className="text-left px-4 py-3">Trials</th>
                <th className="text-left px-4 py-3">Status</th>
                <th className="text-right px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr key={row.id} className="border-t border-gray-100">
                  <td className="px-4 py-3 font-medium text-gray-900">{row.full_name}</td>
                  <td className="px-4 py-3 text-gray-500">{row.email}</td>
                  <td className="px-4 py-3 capitalize">{row.role.replace('_', ' ')}</td>
                  <td className="px-4 py-3 text-gray-500">{row.staff_trials?.length || 0}</td>
                  <td className="px-4 py-3">
                    <span className={row.active ? 'text-green-600' : 'text-gray-400'}>
                      {row.active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => toggleActive(row)}
                      className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-gray-900">
                      {row.active ? <ShieldOff size={14} /> : <ShieldCheck size={14} />}
                      {row.active ? 'Deactivate' : 'Reactivate'}
                    </button>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={6} className="text-center py-10 text-gray-400">No staff accounts yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </PageLayout>
  )
}