-- ClinOps Autopilot: schema adjustments on top of your existing tables
-- Phase 1, corrected. Your tables (trials, patients, proxy_reporters,
-- adverse_events, safety_signals, message_fragments, communications_log)
-- already exist from the schema you ran first. This script does NOT
-- recreate them. It only adds what's missing (updated_at tracking) and
-- indexes on columns confirmed to exist in your actual tables.

create extension if not exists "uuid-ossp";
create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------
-- updated_at trigger helper. Needed here because 002/003 create a
-- trigger on escalation_rules that calls this function.
-- ---------------------------------------------------------------------
create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

-- ---------------------------------------------------------------------
-- trials: add updated_at, wasn't in your original schema
-- ---------------------------------------------------------------------
alter table trials add column if not exists updated_at timestamptz not null default now();
drop trigger if exists trials_set_updated_at on trials;
create trigger trials_set_updated_at before update on trials
    for each row execute function set_updated_at();

-- ---------------------------------------------------------------------
-- patients: add updated_at, plus indexes on your existing columns
-- ---------------------------------------------------------------------
alter table patients add column if not exists updated_at timestamptz not null default now();
drop trigger if exists patients_set_updated_at on patients;
create trigger patients_set_updated_at before update on patients
    for each row execute function set_updated_at();

create index if not exists idx_patients_whatsapp on patients(whatsapp_number);
create index if not exists idx_patients_sms on patients(sms_number);
create index if not exists idx_patients_telegram on patients(telegram_id);
create index if not exists idx_patients_email on patients(email);
create index if not exists idx_patients_trial on patients(trial_id);

-- ---------------------------------------------------------------------
-- proxy_reporters: indexes only, table already matches what the code needs
-- ---------------------------------------------------------------------
create index if not exists idx_proxy_patient on proxy_reporters(patient_id);
create index if not exists idx_proxy_whatsapp on proxy_reporters(whatsapp_number);
create index if not exists idx_proxy_sms on proxy_reporters(sms_number);

-- ---------------------------------------------------------------------
-- adverse_events: add updated_at, plus indexes on your existing columns
-- ---------------------------------------------------------------------
alter table adverse_events add column if not exists updated_at timestamptz not null default now();
drop trigger if exists ae_set_updated_at on adverse_events;
create trigger ae_set_updated_at before update on adverse_events
    for each row execute function set_updated_at();

create index if not exists idx_ae_status on adverse_events(status);
create index if not exists idx_ae_trial on adverse_events(trial_id);
create index if not exists idx_ae_patient on adverse_events(patient_id);
create index if not exists idx_ae_severity on adverse_events(severity);
create index if not exists idx_ae_channel on adverse_events(channel);
create index if not exists idx_ae_created on adverse_events(created_at desc);
-- powers get_open_deadlines(): status in (...) AND submitted_to_regulator = false AND regulatory_deadline is not null
create index if not exists idx_ae_open_deadlines on adverse_events(regulatory_deadline)
    where submitted_to_regulator = false;

-- ---------------------------------------------------------------------
-- safety_signals: indexes only
-- ---------------------------------------------------------------------
create index if not exists idx_signals_trial on safety_signals(trial_id, status);
create index if not exists idx_signals_detection_time on safety_signals(detection_time desc);

-- ---------------------------------------------------------------------
-- message_fragments: indexes only
-- ---------------------------------------------------------------------
create index if not exists idx_fragments_identifier on message_fragments(patient_identifier);
create index if not exists idx_fragments_assembled on message_fragments(assembled) where assembled = false;

-- ---------------------------------------------------------------------
-- communications_log: indexes only (your column is sent_at, not created_at)
-- ---------------------------------------------------------------------
create index if not exists idx_comms_patient on communications_log(patient_id);
create index if not exists idx_comms_ae on communications_log(ae_id);
create index if not exists idx_comms_sent_at on communications_log(sent_at desc);

-- ---------------------------------------------------------------------
-- Row level security: locked down by default. The FastAPI backend uses
-- the service-role key (bypasses RLS), so these policies only matter if
-- the frontend ever talks to Supabase directly. Enable now so nothing
-- is silently public.
-- ---------------------------------------------------------------------
alter table trials enable row level security;
alter table patients enable row level security;
alter table proxy_reporters enable row level security;
alter table adverse_events enable row level security;
alter table safety_signals enable row level security;
alter table message_fragments enable row level security;
alter table communications_log enable row level security;