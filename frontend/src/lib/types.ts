// frontend/src/lib/types.ts
export type Severity = 'Mild' | 'Moderate' | 'Severe' | 'Life-threatening'
export type Status   = 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED' | 'SUBMITTED'
export type Channel = 'whatsapp' | 'sms' | 'telegram' | 'email' | 'physical_mail'

export interface Patient {
  id: string
  patient_code: string
  full_name: string
  language: string
  country: string
  preferred_channel: Channel
  whatsapp_number?: string
  sms_number?: string
  email?: string
}

export interface Trial {
  trial_name: string
  drug_name: string
  regulatory_body: string
  sponsor_email?: string
  pi_email?: string
}

export interface AdverseEvent {
  id: string
  patient_id: string
  channel: Channel
  message_type: string
  original_message: string
    media_url?: string
    transcript?: string
    symptoms: string[]
    severity: Severity
    urgency: string
    category: string
    language_detected: string
    ai_confidence: number
    trad_medicine_flag: boolean
    trad_medicine_type?: string
    trad_medicine_risk?: string
    cultural_flags: string[]
    draft_patient_reply?: string
    draft_report?: Record<string, unknown>
    status: Status
    coordinator_notes?: string
    regulatory_deadline?: string
    drug_batch?: string
    is_proxy_report: boolean
    is_backdated: boolean
    backdated_gap_days: number
    created_at: string
    patients?: Patient
    trials?: Trial
}

export interface SafetySignal {
  id: string
  trial_id: string
  signal_type: string
  affected_patient_count: number
  common_symptoms: string[]
  drug_batch?: string
  detection_time: string
  status: string
  recommendation: string
}

export interface DashboardStats {
  total_aes: number
  pending_approvals: number
  severe_events: number
    open_signals: number
}
