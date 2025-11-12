-- =====================================================================
-- RH: Refactor para modelo relacional (sem JSONB nos dados de usuários)
-- Seguro para reexecução (idempotente).
-- =====================================================================

SET search_path = public;

-- ---------- util: função touch_updated_at ----------
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END$$ LANGUAGE plpgsql;

-- ---------- núcleo: users ----------
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS rg                   TEXT,
  ADD COLUMN IF NOT EXISTS id_funcional         BIGINT,
  ADD COLUMN IF NOT EXISTS data_nascimento      DATE,
  ADD COLUMN IF NOT EXISTS email_institucional  TEXT,
  ADD COLUMN IF NOT EXISTS telefone_principal   TEXT,
  ADD COLUMN IF NOT EXISTS ramal                TEXT,
  ADD COLUMN IF NOT EXISTS endereco             TEXT,
  ADD COLUMN IF NOT EXISTS dependentes_qtde     INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS formacao_nivel_medio BOOLEAN NOT NULL DEFAULT FALSE;

-- ---------- CPF: garantir UNIQUE em users.cpf mesmo se já houver índice parcial homônimo ----------
DO $$
DECLARE
  con_exists     boolean;
  idx_oid        oid;
  idx_is_unique  boolean;
  idx_is_partial boolean;
  idx_cols       text[];
  ok_cols        boolean;
BEGIN
  -- Já existe a constraint 'public.uq_users_cpf'?
  SELECT EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE c.conname = 'uq_users_cpf'
      AND t.relname = 'users'
      AND n.nspname = 'public'
  ) INTO con_exists;

  IF con_exists THEN
    RETURN;
  END IF;

  -- Existe um objeto chamado public.uq_users_cpf (índice)?
  SELECT to_regclass('public.uq_users_cpf') INTO idx_oid;

  IF idx_oid IS NOT NULL THEN
    -- Propriedades do índice
    SELECT x.indisunique, (x.indpred IS NOT NULL)
      INTO idx_is_unique, idx_is_partial
      FROM pg_index x
     WHERE x.indexrelid = idx_oid;

    -- Colunas do índice, na ordem
    SELECT array_agg(att.attname ORDER BY ord.n)
      INTO idx_cols
      FROM pg_index ix
      JOIN LATERAL unnest(ix.indkey) WITH ORDINALITY AS ord(attnum, n) ON TRUE
      JOIN pg_attribute att ON att.attrelid = ix.indrelid AND att.attnum = ord.attnum
     WHERE ix.indexrelid = idx_oid;

    ok_cols := (idx_cols = ARRAY['cpf']);

    IF idx_is_unique AND NOT idx_is_partial AND ok_cols THEN
      -- Índice é compatível: anexar à constraint
      EXECUTE 'ALTER TABLE public.users ADD CONSTRAINT uq_users_cpf UNIQUE USING INDEX uq_users_cpf';
    ELSE
      -- Índice parcial / errado: dropa e cria a constraint do zero
      EXECUTE 'DROP INDEX IF EXISTS public.uq_users_cpf';
      EXECUTE 'ALTER TABLE public.users ADD CONSTRAINT uq_users_cpf UNIQUE (cpf)';
    END IF;
  ELSE
    -- Não há índice nem constraint: cria a constraint (gera índice homônimo)
    EXECUTE 'ALTER TABLE public.users ADD CONSTRAINT uq_users_cpf UNIQUE (cpf)';
  END IF;
END$$;

-- E-mail "case-insensitive" (sem obrigar unicidade global quando NULL)
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_nocase
  ON users (LOWER(email))
  WHERE email IS NOT NULL;

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

-- ---------- employment (vínculo) ----------
DO $$
BEGIN
  -- Se as colunas forem ENUM, usar CAST para text nas CHECKs; funciona para ambos (text/enum).
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chk_employment_type') THEN
    ALTER TABLE employment
      ADD CONSTRAINT chk_employment_type
      CHECK (LOWER((type)::text) IN ('efetivo','comissionado','estagiario'));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chk_employment_status') THEN
    ALTER TABLE employment
      ADD CONSTRAINT chk_employment_status
      CHECK (LOWER((status)::text) IN ('ativo','inativo'));
  END IF;

  -- Alinha com contrato da API: inclui 'termino_estagio'
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chk_employment_inactivity_reason') THEN
    ALTER TABLE employment DROP CONSTRAINT chk_employment_inactivity_reason;
  END IF;

  ALTER TABLE employment
    ADD CONSTRAINT chk_employment_inactivity_reason
    CHECK (inactivity_reason IS NULL OR LOWER((inactivity_reason)::text) IN ('exoneracao','aposentadoria','termino_estagio'));
END$$;

-- Índices úteis
CREATE INDEX IF NOT EXISTS ix_employment_user_active ON employment(user_id) WHERE end_date IS NULL;
CREATE INDEX IF NOT EXISTS ix_employment_kind_status ON employment(type, status);

-- ---------- efetivo: campos adicionais ----------
ALTER TABLE employment_efetivo
  ADD COLUMN IF NOT EXISTS lotacao_portaria                TEXT,
  ADD COLUMN IF NOT EXISTS cedido_de                       TEXT,
  ADD COLUMN IF NOT EXISTS cedido_para                     TEXT,
  ADD COLUMN IF NOT EXISTS classe                          TEXT,
  ADD COLUMN IF NOT EXISTS classe_nivel                    INTEGER,
  ADD COLUMN IF NOT EXISTS estabilidade_data               DATE,
  ADD COLUMN IF NOT EXISTS estabilidade_protocolo          TEXT,
  ADD COLUMN IF NOT EXISTS estabilidade_resolucao_conjunta TEXT,
  ADD COLUMN IF NOT EXISTS estabilidade_publicacao_data    DATE,
  ADD COLUMN IF NOT EXISTS updated_at                      TIMESTAMPTZ NOT NULL DEFAULT now();

DROP TRIGGER IF EXISTS trg_emp_efetivo_touch ON employment_efetivo;
CREATE TRIGGER trg_emp_efetivo_touch
  BEFORE UPDATE ON employment_efetivo
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- Efetivo: capacitações
CREATE TABLE IF NOT EXISTS efetivo_capacitacoes (
  id                 BIGSERIAL PRIMARY KEY,
  employment_id      UUID NOT NULL REFERENCES employment(id) ON DELETE CASCADE,
  protocolo          TEXT,
  curso              TEXT NOT NULL,
  conclusao_data     DATE,
  decreto_numero     TEXT,
  resolucao_conjunta TEXT,
  classe             TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_cap_emp ON efetivo_capacitacoes(employment_id);

-- Efetivo: GITI
CREATE TABLE IF NOT EXISTS efetivo_giti (
  id             BIGSERIAL PRIMARY KEY,
  employment_id  UUID NOT NULL REFERENCES employment(id) ON DELETE CASCADE,
  curso          TEXT NOT NULL,
  conclusao_data DATE,
  tipo           TEXT NOT NULL,  -- graduacao|mestrado|doutorado|pos
  percentual     INTEGER NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (LOWER(tipo) IN ('graduacao','mestrado','doutorado','pos')),
  CHECK (percentual IN (10,15,20))
);
CREATE INDEX IF NOT EXISTS ix_giti_emp ON efetivo_giti(employment_id);

-- Efetivo: outro cargo
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

-- ---------- comissionado ----------
ALTER TABLE employment_comissionado
  ADD COLUMN IF NOT EXISTS funcao_exercida TEXT,
  ADD COLUMN IF NOT EXISTS com_vinculo     BOOLEAN,
  ADD COLUMN IF NOT EXISTS updated_at      TIMESTAMPTZ NOT NULL DEFAULT now();

DROP TRIGGER IF EXISTS trg_emp_comis_touch ON employment_comissionado;
CREATE TRIGGER trg_emp_comis_touch
  BEFORE UPDATE ON employment_comissionado
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- ---------- estagiário ----------
ALTER TABLE employment_estagiario
  ADD COLUMN IF NOT EXISTS inicio_data            DATE,
  ADD COLUMN IF NOT EXISTS fim_data               DATE,
  ADD COLUMN IF NOT EXISTS aditivo_novo_fim_data  DATE,
  ADD COLUMN IF NOT EXISTS rescisao_data          DATE,
  ADD COLUMN IF NOT EXISTS tce_numero             TEXT,
  ADD COLUMN IF NOT EXISTS tce_ano                INTEGER,
  ADD COLUMN IF NOT EXISTS fluxogramas            TEXT,
  ADD COLUMN IF NOT EXISTS frequencia             TEXT,
  ADD COLUMN IF NOT EXISTS pagamento              TEXT,
  ADD COLUMN IF NOT EXISTS vale_transporte        BOOLEAN,
  ADD COLUMN IF NOT EXISTS updated_at             TIMESTAMPTZ NOT NULL DEFAULT now();

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
     WHERE table_schema='public'
       AND table_name='employment_estagiario'
       AND column_name='limite_alerta_data'
  ) THEN
    ALTER TABLE employment_estagiario
      ADD COLUMN limite_alerta_data DATE
      GENERATED ALWAYS AS ( (inicio_data + INTERVAL '2 years')::date ) STORED;
  END IF;
END$$;

DROP TRIGGER IF EXISTS trg_emp_estag_touch ON employment_estagiario;
CREATE TRIGGER trg_emp_estag_touch
  BEFORE UPDATE ON employment_estagiario
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

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

-- ---------- índices de apoio ----------
CREATE INDEX IF NOT EXISTS ix_users_nome ON users (name);
-- (não criamos índice extra em cpf: a UNIQUE constraint já o provê)
CREATE UNIQUE INDEX IF NOT EXISTS uq_org_units_code ON org_units(code);
CREATE INDEX IF NOT EXISTS ix_users_org  ON users (email_institucional);
