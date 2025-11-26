-- ============================================================================
-- Portal AGEPAR — Schema consolidado (PostgreSQL)
-- Idempotente, sem duplicações e sem código de teste.
-- ============================================================================

-- Segurança de contexto
SET search_path = public;

-- Extensões necessárias
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

-- Função de manutenção de updated_at (uso geral)
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- ===============================
-- Autenticação / RBAC / Auditoria
-- ===============================

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

-- Campos adicionais (RH) — seguros para reexecução
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS rg                   TEXT,
  ADD COLUMN IF NOT EXISTS id_funcional         BIGINT,
  ADD COLUMN IF NOT EXISTS data_nascimento      DATE,
  ADD COLUMN IF NOT EXISTS email_institucional  TEXT,
  ADD COLUMN IF NOT EXISTS telefone_principal   TEXT,
  ADD COLUMN IF NOT EXISTS ramal                TEXT,
  ADD COLUMN IF NOT EXISTS endereco             TEXT,
  ADD COLUMN IF NOT EXISTS dependentes_qtde     INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS formacao_nivel_medio BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT TRUE;

-- Unicidade: substituir índices antigos por constraints canônicas
DO $$
BEGIN
  IF to_regclass('public.uq_users_email') IS NOT NULL THEN
    EXECUTE 'DROP INDEX IF EXISTS public.uq_users_email';
  END IF;
  IF to_regclass('public.uq_users_email_nocase') IS NOT NULL THEN
    EXECUTE 'DROP INDEX IF EXISTS public.uq_users_email_nocase';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.users'::regclass AND conname = 'uq_users_email'
  ) THEN
    EXECUTE 'ALTER TABLE public.users ADD CONSTRAINT uq_users_email UNIQUE (email)';
  END IF;

  IF to_regclass('public.uq_users_cpf') IS NOT NULL THEN
    EXECUTE 'DROP INDEX IF EXISTS public.uq_users_cpf';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.users'::regclass AND conname = 'uq_users_cpf'
  ) THEN
    EXECUTE 'ALTER TABLE public.users ADD CONSTRAINT uq_users_cpf UNIQUE (cpf)';
  END IF;
END $$;

-- Trigger updated_at
DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

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

-- LOGIN_ATTEMPTS
CREATE TABLE IF NOT EXISTS login_attempts (
  id BIGSERIAL PRIMARY KEY,
  at TIMESTAMPTZ NOT NULL DEFAULT now(),
  user_id UUID REFERENCES users(id),          -- sem CASCADE (histórico)
  login_identifier TEXT NOT NULL,             -- e-mail/CPF como recebido
  success BOOLEAN NOT NULL,
  reason TEXT,
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
  action TEXT NOT NULL,
  object_type TEXT,
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

-- APP_LOGS (opcional)
CREATE TABLE IF NOT EXISTS app_logs (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  level TEXT NOT NULL CHECK (level IN ('DEBUG','INFO','WARN','ERROR')),
  logger TEXT,
  message TEXT NOT NULL,
  context JSONB NOT NULL DEFAULT '{}'::jsonb,
  request_id UUID,
  user_id UUID REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS ix_app_logs_ts ON app_logs (ts DESC);
CREATE INDEX IF NOT EXISTS ix_app_logs_level ON app_logs (level);
CREATE INDEX IF NOT EXISTS ix_app_logs_context ON app_logs USING GIN (context);

-- Seeds mínimos (dev)
INSERT INTO roles (name, description)
VALUES ('admin','Acesso administrativo'), ('coordenador','Papel de coordenação')
ON CONFLICT (name) DO NOTHING;

WITH upsert AS (
  INSERT INTO users (name, email, status, source, is_superuser, must_change_password, attrs)
  VALUES ('Dev Admin', 'dev@local', 'active', 'local', TRUE, FALSE, '{"seed": true}')
  ON CONFLICT (email) DO UPDATE SET
    name = EXCLUDED.name,
    status = EXCLUDED.status,
    source = EXCLUDED.source,
    is_superuser = EXCLUDED.is_superuser,
    must_change_password = EXCLUDED.must_change_password,
    attrs = EXCLUDED.attrs
  RETURNING id
)
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id FROM upsert u
JOIN roles r ON r.name IN ('admin')
ON CONFLICT DO NOTHING;

INSERT INTO roles(name)
SELECT 'rh'
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name='rh');

-- ===============================
-- Estrutura organizacional e RH
-- ===============================

-- ORG_UNITS
CREATE TABLE IF NOT EXISTS org_units (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_id UUID NULL REFERENCES org_units(id) ON DELETE SET NULL,
  code TEXT UNIQUE NOT NULL,
  name CITEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_org_units_parent ON org_units(parent_id);
-- Para CITEXT, índice direto na coluna é suficiente para igualdade case-insensitive
CREATE INDEX IF NOT EXISTS idx_org_units_name ON org_units(name);

DROP TRIGGER IF EXISTS trg_org_units_updated_at ON org_units;
CREATE TRIGGER trg_org_units_updated_at
BEFORE UPDATE ON org_units
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Tipos de vínculo
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'employment_type') THEN
    CREATE TYPE employment_type AS ENUM ('efetivo','comissionado','estagiario');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'employment_status') THEN
    CREATE TYPE employment_status AS ENUM ('ativo','inativo');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'inactivity_reason') THEN
    CREATE TYPE inactivity_reason AS ENUM ('exoneracao','aposentadoria','termino_estagio');
  END IF;
END $$;

-- EMPLOYMENT (base)
CREATE TABLE IF NOT EXISTS employment (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type employment_type NOT NULL,
  status employment_status NOT NULL,
  inactivity_reason inactivity_reason NULL,
  org_unit_id UUID NOT NULL REFERENCES org_units(id) ON DELETE RESTRICT,
  start_date DATE NULL,
  end_date DATE NULL,
  attrs JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_inactivity_reason
    CHECK ((status = 'inativo' AND inactivity_reason IS NOT NULL)
        OR (status = 'ativo'   AND inactivity_reason IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_employment_user ON employment(user_id);
CREATE INDEX IF NOT EXISTS idx_employment_org  ON employment(org_unit_id);
CREATE INDEX IF NOT EXISTS idx_employment_type_status ON employment(type, status);
CREATE INDEX IF NOT EXISTS ix_employment_user_active ON employment(user_id) WHERE end_date IS NULL;

DROP TRIGGER IF EXISTS trg_employment_updated_at ON employment;
CREATE TRIGGER trg_employment_updated_at
BEFORE UPDATE ON employment
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Especializações
CREATE TABLE IF NOT EXISTS employment_efetivo (
  employment_id UUID PRIMARY KEY REFERENCES employment(id) ON DELETE CASCADE,
  decreto_nomeacao_numero TEXT NULL,
  decreto_nomeacao_data   DATE NULL,
  posse_data              DATE NULL,
  exercicio_data          DATE NULL,
  classe                  TEXT NULL,
  lotacao_portaria        TEXT NULL,
  cedido_de               TEXT NULL,
  cedido_para             TEXT NULL,
  estabilidade_data               DATE NULL,
  estabilidade_protocolo          TEXT NULL,
  estabilidade_resolucao_conjunta TEXT NULL,
  estabilidade_publicacao_data    DATE NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS trg_emp_efetivo_touch ON employment_efetivo;
CREATE TRIGGER trg_emp_efetivo_touch
BEFORE UPDATE ON employment_efetivo
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS employment_comissionado (
  employment_id UUID PRIMARY KEY REFERENCES employment(id) ON DELETE CASCADE,
  decreto_nomeacao_numero   TEXT NULL,
  decreto_nomeacao_data     DATE NULL,
  posse_data                DATE NULL,
  exercicio_data            DATE NULL,
  simbolo                   TEXT NULL,
  decreto_exoneracao_numero TEXT NULL,
  decreto_exoneracao_data   DATE NULL,
  com_vinculo               BOOLEAN NULL,
  funcao_exercida           TEXT NULL,
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS trg_emp_comis_touch ON employment_comissionado;
CREATE TRIGGER trg_emp_comis_touch
BEFORE UPDATE ON employment_comissionado
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS employment_estagiario (
  employment_id UUID PRIMARY KEY REFERENCES employment(id) ON DELETE CASCADE,
  tce_numero   TEXT NULL,
  tce_ano      INTEGER NULL,
  inicio_data  DATE NULL,
  fim_data     DATE NULL,
  aditivo_novo_fim_data DATE NULL,
  rescisao_data        DATE NULL,
  fluxogramas   TEXT,
  frequencia    TEXT,
  pagamento     TEXT,
  vale_transporte BOOLEAN,
  limite_alerta_data DATE GENERATED ALWAYS AS ((COALESCE(aditivo_novo_fim_data, fim_data) - INTERVAL '1 month')::date) STORED,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS trg_emp_estag_touch ON employment_estagiario;
CREATE TRIGGER trg_emp_estag_touch
BEFORE UPDATE ON employment_estagiario
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Tabelas auxiliares (efetivo)
CREATE TABLE IF NOT EXISTS efetivo_capacitacoes (
  id            BIGSERIAL PRIMARY KEY,
  employment_id UUID NOT NULL REFERENCES employment(id) ON DELETE CASCADE,
  protocolo          TEXT,
  curso              TEXT NOT NULL,
  conclusao_data     DATE,
  decreto_numero     TEXT,
  resolucao_conjunta TEXT,
  classe             TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_cap_emp ON efetivo_capacitacoes(employment_id);

CREATE TABLE IF NOT EXISTS efetivo_giti (
  id            BIGSERIAL PRIMARY KEY,
  employment_id UUID NOT NULL REFERENCES employment(id) ON DELETE CASCADE,
  curso         TEXT NOT NULL,
  conclusao_data DATE,
  tipo          TEXT NOT NULL,  -- graduacao|mestrado|doutorado|pos
  percentual    INTEGER NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (LOWER(tipo) IN ('graduacao','mestrado','doutorado','pos')),
  CHECK (percentual IN (10,15,20))
);
CREATE INDEX IF NOT EXISTS ix_giti_emp ON efetivo_giti(employment_id);

CREATE TABLE IF NOT EXISTS employment_efetivo_outro_cargo (
  id                        BIGSERIAL PRIMARY KEY,
  employment_id             UUID NOT NULL REFERENCES employment(id) ON DELETE CASCADE,
  funcao_ou_cc              TEXT,
  decreto_nomeacao_numero   TEXT,
  decreto_nomeacao_data     DATE,
  posse_data                DATE,
  exercicio_data            DATE,
  simbolo                   TEXT,
  decreto_exoneracao_numero TEXT,
  decreto_exoneracao_data   DATE,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_emp_efetivo_outro_emp ON employment_efetivo_outro_cargo(employment_id);

-- USER x ORG_UNITS (N:N)
CREATE TABLE IF NOT EXISTS user_org_units (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  org_unit_id UUID NOT NULL REFERENCES org_units(id) ON DELETE CASCADE,
  primary_flag BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, org_unit_id)
);
CREATE INDEX IF NOT EXISTS idx_user_org_units_user ON user_org_units(user_id);
CREATE INDEX IF NOT EXISTS idx_user_org_units_org  ON user_org_units(org_unit_id);

-- ---------- formação (comum) ----------
CREATE TABLE IF NOT EXISTS user_education_graduacao (
  id             BIGSERIAL PRIMARY KEY,
  user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  curso          TEXT NOT NULL,
  instituicao    TEXT,
  conclusao_data DATE,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_u_edu_grad_user ON user_education_graduacao(user_id);

CREATE TABLE IF NOT EXISTS user_education_posgrad (
  id             BIGSERIAL PRIMARY KEY,
  user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  curso          TEXT NOT NULL,
  tipo           TEXT, -- especializacao|mestrado|doutorado|pos
  instituicao    TEXT,
  conclusao_data DATE,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (tipo IS NULL OR LOWER(tipo) IN ('especializacao','mestrado','doutorado','pos'))
);
CREATE INDEX IF NOT EXISTS ix_u_edu_pos_user ON user_education_posgrad(user_id);

-- ---------- visão para consultas do RH ----------
CREATE OR REPLACE VIEW v_rh_users AS
SELECT
  u.id::text               AS id,
  u.name                   AS nome_completo,
  u.cpf,
  u.email                  AS email_principal,
  u.email_institucional,
  u.telefone_principal,
  u.ramal,
  u.endereco,
  u.dependentes_qtde,
  u.formacao_nivel_medio,
  u.status                 AS status_usuario, -- active|blocked|pending
  e.type                   AS tipo_vinculo,   -- efetivo|comissionado|estagiario
  e.status                 AS status_vinculo, -- ativo|inativo
  e.inactivity_reason      AS motivo_inatividade,
  ou.code                  AS org_code,
  ou.name                  AS org_name
FROM users u
LEFT JOIN employment e ON e.user_id = u.id AND e.end_date IS NULL
LEFT JOIN org_units ou ON ou.id = e.org_unit_id;

-- Seeds de org_units (raiz, filhas, netas)
BEGIN;
INSERT INTO org_units(code, name, parent_id)
VALUES ('AGEPAR','AGEPAR', NULL)
ON CONFLICT (code) DO NOTHING;

INSERT INTO org_units(code, name, parent_id)
SELECT v.code, v.name, p.id
FROM (VALUES
  ('AGEPAR-GOV','Governança'),
  ('AGEPAR-TI','Tecnologia da Informação')
) AS v(code, name)
JOIN org_units p ON p.code = 'AGEPAR'
LEFT JOIN org_units u ON u.code = v.code
WHERE u.id IS NULL;

INSERT INTO org_units(code, name, parent_id)
SELECT x.code, x.name, p.id
FROM (VALUES
  ('GOV-RH','Recursos Humanos','AGEPAR-GOV'),
  ('GOV-COMPRAS','Compras & Contratos','AGEPAR-GOV'),
  ('GOV-JUR','Jurídico','AGEPAR-GOV'),
  ('GOV-OUV','Ouvidoria','AGEPAR-GOV'),
  ('TI-DEV','Desenvolvimento','AGEPAR-TI'),
  ('TI-INFRA','Infraestrutura','AGEPAR-TI')
) AS x(code, name, parent_code)
JOIN org_units p ON p.code = x.parent_code
LEFT JOIN org_units u ON u.code = x.code
WHERE u.id IS NULL;
COMMIT;

-- Índices de apoio finais
CREATE INDEX IF NOT EXISTS ix_users_nome ON users (name);
-- A UNIQUE constraint em org_units(code) já cria índice; não recriar.
CREATE INDEX IF NOT EXISTS ix_users_org ON users (email_institucional);
