-- ════════════════════════════════════════════════════════
-- 003: TELEGRAM CONTACT FOR STAFF + DEFAULT ESCALATION SEED
-- Run after 002. Reproduces the exact routing that used to be hardcoded
-- in notifications.py, as default (trial_id IS NULL) escalation_rules,
-- so behavior doesn't silently change when this ships. Adjust or add
-- trial-specific rules afterward via the /api/escalation-rules endpoint
-- or directly in this table.
-- ════════════════════════════════════════════════════════

ALTER TABLE staff ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR(50);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM escalation_rules) THEN
        INSERT INTO escalation_rules
            (trial_id, severity, category, timing, recipient_role, channel)
        VALUES
            -- immediate, pre-approval (mirrors the old notify_coordinator_urgent)
            (NULL, 'Severe',           'ANY', 'immediate', 'coordinator', 'whatsapp'),
            (NULL, 'Life-threatening', 'ANY', 'immediate', 'coordinator', 'whatsapp'),
            (NULL, 'Life-threatening', 'ANY', 'immediate', 'pi',          'email'),
            (NULL, 'Life-threatening', 'ANY', 'immediate', 'pi',          'whatsapp'),

            -- after approval (mirrors the old notify_after_approval)
            (NULL, 'Severe',           'ANY', 'after_approval', 'sponsor',     'email'),
            (NULL, 'Life-threatening', 'ANY', 'after_approval', 'sponsor',     'email'),
            (NULL, 'ANY',              'ANY', 'after_approval', 'coordinator', 'whatsapp'),

            -- safety signals (mirrors the old notify_safety_signal)
            (NULL, 'ANY', 'SAFETY_SIGNAL', 'immediate', 'coordinator', 'whatsapp'),
            (NULL, 'ANY', 'SAFETY_SIGNAL', 'immediate', 'sponsor',     'email'),
            (NULL, 'ANY', 'SAFETY_SIGNAL', 'immediate', 'pi',          'whatsapp');
    END IF;
END $$;