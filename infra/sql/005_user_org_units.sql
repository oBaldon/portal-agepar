-- 005_user_org_units.sql
-- Lotação adicional (N:N)

CREATE TABLE IF NOT EXISTS user_org_units (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  org_unit_id UUID NOT NULL REFERENCES org_units(id) ON DELETE CASCADE,
  primary_flag BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, org_unit_id)
);

CREATE INDEX IF NOT EXISTS idx_user_org_units_user ON user_org_units(user_id);
CREATE INDEX IF NOT EXISTS idx_user_org_units_org ON user_org_units(org_unit_id);