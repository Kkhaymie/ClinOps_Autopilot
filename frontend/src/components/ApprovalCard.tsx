// frontend/src/components/ApprovalCard.tsx
'use client'
import { useState } from 'react'
import { AdverseEvent } from '@/lib/types'
import { SeverityBadge } from './SeverityBadge'
import { TradMedicineAlert } from './TradMedicineAlert'
import { api } from '@/lib/api'
import {
  channelIcon, channelLabel, timeAgo,
  severityBorder
} from '@/lib/utils'
import {
  CheckCircle, XCircle, Edit2,
  Mic, Video, Image, FileText
} from 'lucide-react'

interface Props {
  ae: AdverseEvent
  onAction: () => void
}

const typeIcon = {
  audio: <Mic   size={14} className="text-blue-500" />,
  video: <Video size={14} className="text-purple-500" />,
  image: <Image size={14} className="text-green-500" />,
  text: <FileText size={14} className="text-gray-400" />,
}

export function ApprovalCard({ ae, onAction }: Props) {
  const [editing, setEditing]   = useState(false)
  const [reply, setReply]       = useState(ae.draft_patient_reply || '')
  const [notes, setNotes]       = useState('')
const [loading, setLoading]   = useState(false)

async function handleApprove() {
  setLoading(true)
  try {
    await api.approve(ae.id, notes || undefined)
    onAction()
  } catch (e) {
    console.error(e)
  } finally {
    setLoading(false)
  }
}

async function handleReject() {
  setLoading(true)
  try {
    await api.reject(ae.id, notes || 'Rejected by coordinator')
    onAction()
  } catch (e) {
    console.error(e)
  } finally {
    setLoading(false)
  }
}

const patient = ae.patients
const trial   = ae.trials

return (
  <div className={`bg-white rounded-xl border border-gray-100
                   border-l-4 ${severityBorder(ae.severity)}
                   shadow-sm p-5 space-y-4`}>

   {/* ── HEADER ──────────────────────────────────────── */}
   <div className="flex items-start justify-between gap-3">
     <div className="flex items-center gap-2 flex-wrap">
       <span className="text-lg">
         {channelIcon(ae.channel)}
       </span>
       <span className="font-semibold text-gray-900 text-sm">
         {patient?.patient_code ?? 'Unknown'}
       </span>
    <span className="text-gray-400 text-xs">
      {patient?.full_name}
    </span>
    <span className="text-gray-300">·</span>
    <span className="text-xs text-gray-400">
      {channelLabel(ae.channel)}
    </span>
    <span className="text-gray-300">·</span>
    <span className="flex items-center gap-1 text-xs text-gray-400">
      {typeIcon[ae.message_type as keyof typeof typeIcon]}
      {ae.message_type}
    </span>
  </div>
  <div className="flex items-center gap-2 shrink-0">
    <SeverityBadge severity={ae.severity} />
    <span className="text-xs text-gray-400">
      {timeAgo(ae.created_at)}
    </span>
  </div>
</div>

{/* ── ORIGINAL MESSAGE ────────────────────────────── */}
<div className="bg-gray-50 rounded-lg px-4 py-3 text-sm
                text-gray-700 leading-relaxed border
                border-gray-100">
  <p className="text-[10px] text-gray-400 uppercase
                tracking-wide mb-1 font-medium">
    Original message
  </p>
  "{ae.original_message}"
  {ae.transcript && ae.transcript !== ae.original_message && (
    <p className="mt-2 pt-2 border-t border-gray-200
                  text-xs text-gray-500 italic">
      Transcript: {ae.transcript}
    </p>
  )}
</div>

{/* ── AI ANALYSIS ─────────────────────────────────── */}
<div className="grid grid-cols-2 gap-3 text-sm">
  <div>
    <p className="text-[10px] uppercase tracking-wide
                  text-gray-400 font-medium mb-1">
    Symptoms detected
  </p>
  <div className="flex flex-wrap gap-1">
    {ae.symptoms.length > 0
      ? ae.symptoms.map(s => (
          <span key={s}
            className="bg-blue-50 text-blue-700 text-xs
                       px-2 py-0.5 rounded-full">
            {s}
          </span>
        ))
      : <span className="text-gray-400 text-xs">None detected</span>
    }
  </div>
</div>
<div className="space-y-1.5">
  <div>
    <p className="text-[10px] uppercase tracking-wide
                  text-gray-400 font-medium">
      Language
    </p>
    <p className="text-xs text-gray-700">
      {ae.language_detected}
    </p>
  </div>
  <div>
    <p className="text-[10px] uppercase tracking-wide
                  text-gray-400 font-medium">
      AI Confidence
    </p>
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-gray-200 rounded-full h-1.5">
        <div
          className="bg-blue-500 h-1.5 rounded-full"
          style={{ width: `${ae.ai_confidence}%` }}
        />
      </div>
      <span className="text-xs text-gray-500">
        {ae.ai_confidence}%
      </span>
    </div>
  </div>
  {trial && (
      <div>
        <p className="text-[10px] uppercase tracking-wide
                      text-gray-400 font-medium">
          Drug
        </p>
        <p className="text-xs text-gray-700">{trial.drug_name}</p>
      </div>
    )}
  </div>
</div>

{/* ── FLAGS ───────────────────────────────────────── */}
<div className="space-y-2">
  {ae.trad_medicine_flag && ae.trad_medicine_type && (
    <TradMedicineAlert
      type={ae.trad_medicine_type}
      risk={ae.trad_medicine_risk || 'UNKNOWN'}
    />
  )}
  {ae.is_backdated && ae.backdated_gap_days > 0 && (
    <div className="bg-red-50 border border-red-400
                     text-red-800 text-sm px-3 py-2 rounded-lg">
      ⚠️ <span className="font-semibold">Backdated Event</span>
       {' '}— Letter written{' '}
       <span className="font-semibold">
         {ae.backdated_gap_days} days ago
       </span>
       . Regulatory clock may have already started.
    </div>
  )}
  {ae.is_proxy_report && (
    <div className="bg-blue-50 border border-blue-300
                     text-blue-800 text-xs px-3 py-2 rounded-lg">
      👥 This report was submitted by a family member
       (proxy reporter) on the patient's behalf.
    </div>
  )}
  {ae.cultural_flags && ae.cultural_flags.length > 0 && (
    <div className="bg-purple-50 border border-purple-200
                     text-purple-800 text-xs px-3 py-2 rounded-lg">
      🌍{' '}
       {ae.cultural_flags.join(' · ')}
    </div>
  )}
</div>

{/* ── DRAFT REPLY ─────────────────────────────────── */}
<div>
  <div className="flex items-center justify-between mb-1.5">
    <p className="text-[10px] uppercase tracking-wide
                   text-gray-400 font-medium">
       Draft patient reply
    </p>
    <button
      onClick={() => setEditing(e => !e)}
      className="text-[10px] text-blue-500 hover:text-blue-700
                  flex items-center gap-1"
    >
       <Edit2 size={10} />
       {editing ? 'Done' : 'Edit'}
    </button>
  </div>
  {editing ? (
    <textarea
      className="w-full text-sm border border-gray-200
                  rounded-lg px-3 py-2 resize-none h-20
                  focus:outline-none focus:ring-2
                  focus:ring-blue-200"
      value={reply}
      onChange={e => setReply(e.target.value)}
    />
  ) : (
    <div className="bg-green-50 border border-green-100
                     rounded-lg px-3 py-2 text-sm text-gray-700">
       {reply || '—'}
    </div>
  )}
</div>

{/* ── COORDINATOR NOTES ───────────────────────────── */}
<div>
  <p className="text-[10px] uppercase tracking-wide
                text-gray-400 font-medium mb-1.5">
    Coordinator notes (optional)
  </p>
  <textarea
             className="w-full text-sm border border-gray-200
                        rounded-lg px-3 py-2 resize-none h-16
                        focus:outline-none focus:ring-2
                        focus:ring-blue-200"
             placeholder="Add notes before approving..."
             value={notes}
             onChange={e => setNotes(e.target.value)}
           />
         </div>

          {/* ── ACTION BUTTONS ──────────────────────────────── */}
          <div className="flex gap-3 pt-1">
            <button
              onClick={handleApprove}
              disabled={loading}
              className="flex-1 flex items-center justify-center gap-2
                         bg-green-600 hover:bg-green-700 text-white
                         font-semibold py-2.5 px-4 rounded-lg text-sm
                         transition-colors disabled:opacity-50"
            >
              <CheckCircle size={16} />
              {loading ? 'Processing...' : 'Approve & Send'}
            </button>
            <button
              onClick={handleReject}
              disabled={loading}
              className="flex items-center justify-center gap-2
                         border border-red-300 text-red-600
                         hover:bg-red-50 font-medium py-2.5 px-4
                         rounded-lg text-sm transition-colors
                         disabled:opacity-50"
            >
              <XCircle size={16} />
              Reject
            </button>
          </div>
        </div>
    )
}
