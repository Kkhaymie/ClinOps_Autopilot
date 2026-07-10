-- ════════════════════════════════════════════════════════
-- 004: COMPLIANCE CLOCK ESCALATION
-- Run after 003. Adds the column the clock uses to avoid re-alerting
-- every hour at the same threshold, and seeds default routing for
-- deadline warnings so the clock has somewhere to send alerts out of
-- the box.
-- ════════════════════════════════════════════════════════

ALTER TABLE adverse_events ADD COLUMN IF NOT EXISTS last_deadline_alert_level VARCHAR(20);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM escalation_rules WHERE category LIKE 'DEADLINE_%') THEN
        INSERT INTO escalation_rules
            (trial_id, severity, category, timing, recipient_role, channel)
        VALUES
            (NULL, 'ANY', 'DEADLINE_WARNING', 'immediate', 'coordinator', 'whatsapp'),
            (NULL, 'ANY', 'DEADLINE_URGENT',  'immediate', 'coordinator', 'whatsapp'),
            (NULL, 'ANY', 'DEADLINE_URGENT',  'immediate', 'pi',          'email'),
            (NULL, 'ANY', 'DEADLINE_MISSED',  'immediate', 'coordinator', 'whatsapp'),
            (NULL, 'ANY', 'DEADLINE_MISSED',  'immediate', 'pi',          'email'),
            (NULL, 'ANY', 'DEADLINE_MISSED',  'immediate', 'sponsor',     'email');
    END IF;
END $$;