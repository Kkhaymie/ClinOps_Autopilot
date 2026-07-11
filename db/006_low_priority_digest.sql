-- ════════════════════════════════════════════════════════
-- 006: LOW-PRIORITY BATCHING DIGEST (Scenario 2)
-- Run after 005. No schema changes, just default routing for the new
-- DAILY_DIGEST category the compliance_clock's new scheduled job fires.
-- No new columns needed: the digest query filters on severity/urgency/
-- status, which already exist.
-- ════════════════════════════════════════════════════════

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM escalation_rules WHERE category = 'DAILY_DIGEST') THEN
        INSERT INTO escalation_rules (trial_id, severity, category, timing, recipient_role, channel)
        VALUES (NULL, 'Mild', 'DAILY_DIGEST', 'immediate', 'coordinator', 'email');
    END IF;
END $$;