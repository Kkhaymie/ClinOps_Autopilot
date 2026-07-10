-- ════════════════════════════════════════════════════════
-- 005: UNREGISTERED SENDER LOG, RESPONSE SLA, EMOTIONAL DISTRESS
-- Run after 004.
-- ════════════════════════════════════════════════════════

-- ── Fix #1: unregistered senders no longer vanish ──────────────────
-- Every channel currently replies "we couldn't find your registration"
-- and discards the message. This table catches it instead, so a real
-- patient texting from an unregistered/borrowed phone isn't lost.
CREATE TABLE IF NOT EXISTS unregistered_reports (
    id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    channel          VARCHAR(30) NOT NULL,
    raw_identifier   TEXT NOT NULL,        -- phone number / email / telegram id, as received
    message_type     VARCHAR(20) NOT NULL DEFAULT 'text',
    message_content  TEXT,
    media_url        TEXT,
    reviewed         BOOLEAN NOT NULL DEFAULT FALSE,
    reviewed_by      UUID,
    reviewed_at      TIMESTAMPTZ,
    resolution_notes TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_unregistered_reviewed ON unregistered_reports(reviewed) WHERE reviewed = false;
ALTER TABLE unregistered_reports ENABLE ROW LEVEL SECURITY;

-- ── Fix #2: internal response-time SLA, separate from the regulatory
-- deadline. A Life-threatening report shouldn't wait days (the legal
-- reporting window) for someone to even look at it.
ALTER TABLE adverse_events ADD COLUMN IF NOT EXISTS last_sla_alert_level VARCHAR(20);

-- ── Scenario follow-up: emotional distress / mental health flag ────
ALTER TABLE adverse_events ADD COLUMN IF NOT EXISTS emotional_distress_flag BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE adverse_events ADD COLUMN IF NOT EXISTS emotional_distress_notes TEXT;
CREATE INDEX IF NOT EXISTS idx_ae_emotional_distress ON adverse_events(emotional_distress_flag) WHERE emotional_distress_flag = true;

-- ── Default escalation routing for the two new alert categories ────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM escalation_rules WHERE category = 'UNREGISTERED_SENDER') THEN
        INSERT INTO escalation_rules (trial_id, severity, category, timing, recipient_role, channel)
        VALUES (NULL, 'ANY', 'UNREGISTERED_SENDER', 'immediate', 'coordinator', 'whatsapp');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM escalation_rules WHERE category LIKE 'RESPONSE_SLA_%') THEN
        INSERT INTO escalation_rules (trial_id, severity, category, timing, recipient_role, channel)
        VALUES
            (NULL, 'ANY', 'RESPONSE_SLA_WARNING',  'immediate', 'coordinator', 'whatsapp'),
            (NULL, 'ANY', 'RESPONSE_SLA_URGENT',   'immediate', 'coordinator', 'whatsapp'),
            (NULL, 'ANY', 'RESPONSE_SLA_BREACHED', 'immediate', 'coordinator', 'whatsapp'),
            (NULL, 'ANY', 'RESPONSE_SLA_BREACHED', 'immediate', 'pi',          'email');
    END IF;
END $$;