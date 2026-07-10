-- ════════════════════════════════════════════════════════
-- 002: STAFF ACCOUNTS, ROLES, TRIAL SCOPING, ESCALATION RULES
-- Builds on the schema you already ran. Uses Supabase's built-in
-- auth.users table (created automatically by Supabase Auth) as the
-- identity source; `staff` is the app-level profile on top of it.
-- ════════════════════════════════════════════════════════

do $$ begin
    create type staff_role as enum ('admin','coordinator','pi','sponsor','site_staff');
exception when duplicate_object then null;
end $$;

-- STAFF PROFILES
CREATE TABLE IF NOT EXISTS staff (
    id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email       VARCHAR(100) NOT NULL,
    full_name   VARCHAR(100) NOT NULL,
    role        staff_role NOT NULL,
    phone       VARCHAR(25),
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- WHICH TRIALS A PI / SPONSOR / SITE_STAFF CAN SEE
-- (admin and coordinator ignore this table, they see every trial;
-- enforced in the FastAPI layer, see note on RLS below)
CREATE TABLE IF NOT EXISTS staff_trials (
    staff_id  UUID NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
    trial_id  UUID NOT NULL REFERENCES trials(id) ON DELETE CASCADE,
    PRIMARY KEY (staff_id, trial_id)
);

-- CONFIGURABLE ESCALATION ROUTING
-- Replaces the hardcoded severity-to-recipient logic in notifications.py.
-- trial_id NULL = default rule applied to every trial that has no
-- trial-specific rule for the same severity/category.
CREATE TABLE IF NOT EXISTS escalation_rules (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    trial_id        UUID REFERENCES trials(id) ON DELETE CASCADE,
    severity        VARCHAR(20) NOT NULL,   -- Mild | Moderate | Severe | Life-threatening | ANY
    category        VARCHAR(30) NOT NULL DEFAULT 'ANY',
    timing          VARCHAR(20) NOT NULL DEFAULT 'immediate'
                    CHECK (timing IN ('immediate','after_approval')),
    recipient_role  staff_role NOT NULL,
    channel         VARCHAR(20) NOT NULL CHECK (channel IN ('whatsapp','sms','email','telegram')),
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_escalation_trial ON escalation_rules(trial_id);
CREATE INDEX IF NOT EXISTS idx_escalation_severity ON escalation_rules(severity, category);

CREATE TRIGGER escalation_rules_set_updated_at BEFORE UPDATE ON escalation_rules
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- TIE APPROVALS AND STAFF-SUBMITTED REPORTS TO REAL IDENTITIES
-- (approved_by stays as-is for display/back-compat; approved_by_id is
-- the source of truth going forward)
ALTER TABLE adverse_events ADD COLUMN IF NOT EXISTS approved_by_id UUID REFERENCES staff(id);
ALTER TABLE adverse_events ADD COLUMN IF NOT EXISTS submitted_by_staff_id UUID REFERENCES staff(id);
CREATE INDEX IF NOT EXISTS idx_ae_submitted_by_staff ON adverse_events(submitted_by_staff_id);

-- ── ROW LEVEL SECURITY ──────────────────────────────────────────
-- IMPORTANT: the FastAPI backend connects with the Supabase
-- service-role key, which bypasses RLS entirely. These policies are a
-- backstop for any future direct frontend-to-Supabase calls, not the
-- enforcement mechanism for the API. Enforcement for the API happens
-- in backend/auth/dependencies.py.

ALTER TABLE staff ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_trials ENABLE ROW LEVEL SECURITY;
ALTER TABLE escalation_rules ENABLE ROW LEVEL SECURITY;

CREATE POLICY staff_read_own ON staff FOR SELECT
    USING (id = auth.uid());

CREATE POLICY staff_admin_all ON staff FOR ALL
    USING (EXISTS (SELECT 1 FROM staff s WHERE s.id = auth.uid() AND s.role = 'admin'));

CREATE POLICY escalation_read_all ON escalation_rules FOR SELECT
    USING (EXISTS (SELECT 1 FROM staff s WHERE s.id = auth.uid() AND s.active));

CREATE POLICY escalation_write_admin_coordinator ON escalation_rules FOR ALL
    USING (EXISTS (SELECT 1 FROM staff s WHERE s.id = auth.uid() AND s.role IN ('admin','coordinator')));

-- adverse_events: role- and trial-scoped, same backstop caveat as above
CREATE POLICY ae_admin_coordinator_all ON adverse_events FOR ALL
    USING (EXISTS (SELECT 1 FROM staff s WHERE s.id = auth.uid() AND s.role IN ('admin','coordinator')));

CREATE POLICY ae_trial_scoped_read ON adverse_events FOR SELECT
    USING (EXISTS (
        SELECT 1 FROM staff s
        JOIN staff_trials st ON st.staff_id = s.id
        WHERE s.id = auth.uid() AND s.active
          AND st.trial_id = adverse_events.trial_id
          AND s.role IN ('pi','sponsor')
    ));

CREATE POLICY ae_site_staff_own_submissions ON adverse_events FOR SELECT
    USING (submitted_by_staff_id = auth.uid());

CREATE POLICY ae_site_staff_insert ON adverse_events FOR INSERT
    WITH CHECK (EXISTS (SELECT 1 FROM staff s WHERE s.id = auth.uid() AND s.role = 'site_staff'));