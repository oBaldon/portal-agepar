-- Extensões necessárias (idempotentes)
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

-- Função/trigger para updated_at
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END; $$;

-- USERS
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cpf CHAR(11),
  email CITEXT,
  name TEXT NOT NULL,
  password_hash TEXT,                          -- obrigatório quando source='local'
  phone TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','blocked','pending')),
  source TEXT NOT NULL DEFAULT 'local' CHECK (source IN ('local','eprotocolo')),
  is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
  attrs JSONB NOT NULL DEFAULT '{}'::jsonb,
  last_login_at TIMESTAMPTZ,
  verified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT users_cpf_format CHECK (cpf IS NULL OR cpf ~ '^[0-9]{11}$')
);

-- Índices únicos parciais (aceita NULL)
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_cpf ON users (cpf) WHERE cpf IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email ON users (email) WHERE email IS NOT NULL;

-- Trigger updated_at (idempotente)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_trigger t
    JOIN pg_class c ON c.oid = t.tgrelid
    WHERE t.tgname = 'trg_users_updated_at'
      AND c.relname = 'users'
  ) THEN
    CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
  END IF;
END $$;

-- ROLES
CREATE TABLE IF NOT EXISTS roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- USER_ROLES
CREATE TABLE IF NOT EXISTS user_roles (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, role_id)
);

-- AUTH_SESSIONS
CREATE TABLE IF NOT EXISTS auth_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  ip INET,
  user_agent TEXT,
  csrf_token UUID NOT NULL DEFAULT gen_random_uuid()
);
CREATE INDEX IF NOT EXISTS ix_auth_sessions_user ON auth_sessions (user_id);
CREATE INDEX IF NOT EXISTS ix_auth_sessions_exp ON auth_sessions (expires_at);

-- LOGIN_ATTEMPTS (auditoria e antifraude)
CREATE TABLE IF NOT EXISTS login_attempts (
  id BIGSERIAL PRIMARY KEY,
  at TIMESTAMPTZ NOT NULL DEFAULT now(),
  user_id UUID REFERENCES users(id),          -- sem CASCADE (histórico); testes devem limpar/atualizar
  login_identifier TEXT NOT NULL,             -- email ou cpf como recebido (normalizado a critério da app)
  success BOOLEAN NOT NULL,
  reason TEXT,                                -- ex.: "bad_credentials", "blocked", "rate_limited"
  ip INET,
  user_agent TEXT
);
CREATE INDEX IF NOT EXISTS ix_login_attempts_at ON login_attempts (at DESC);
CREATE INDEX IF NOT EXISTS ix_login_attempts_ident ON login_attempts (login_identifier);

-- AUDIT_EVENTS
CREATE TABLE IF NOT EXISTS audit_events (
  id BIGSERIAL PRIMARY KEY,
  at TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor_user_id UUID REFERENCES users(id),
  action TEXT NOT NULL,             -- ex.: "auth.login", "user.register", "automation.submit"
  object_type TEXT,                 -- ex.: "submission", "document"
  object_id TEXT,
  message TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  ip INET,
  user_agent TEXT,
  request_id UUID
);
CREATE INDEX IF NOT EXISTS ix_audit_events_at ON audit_events (at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_events_action ON audit_events (action);
CREATE INDEX IF NOT EXISTS ix_audit_events_actor ON audit_events (actor_user_id);
CREATE INDEX IF NOT EXISTS ix_audit_events_meta ON audit_events USING GIN (metadata);

-- APP_LOGS (logs de aplicação estruturados)
CREATE TABLE IF NOT EXISTS app_logs (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  level TEXT NOT NULL CHECK (level IN ('DEBUG','INFO','WARN','ERROR')),
  logger TEXT,                      -- nome do logger/ módulo
  message TEXT NOT NULL,
  context JSONB NOT NULL DEFAULT '{}'::jsonb,
  request_id UUID,
  user_id UUID REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS ix_app_logs_ts ON app_logs (ts DESC);
CREATE INDEX IF NOT EXISTS ix_app_logs_level ON app_logs (level);
CREATE INDEX IF NOT EXISTS ix_app_logs_context ON app_logs USING GIN (context);

-- VIEW de compatibilidade com "audits"
CREATE OR REPLACE VIEW audits AS
SELECT
  id,
  at AS created_at,
  actor_user_id AS user_id,
  action,
  object_type,
  object_id,
  message,
  metadata
FROM audit_events;
