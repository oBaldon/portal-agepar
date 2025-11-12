-- 004_employment.sql
-- Vínculos funcionais por usuário, com especializações por tipo

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

-- Base de vínculo (histórico possível)
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
    CHECK ((status = 'inativo' AND inactivity_reason IS NOT NULL) OR (status = 'ativo' AND inactivity_reason IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_employment_user ON employment(user_id);
CREATE INDEX IF NOT EXISTS idx_employment_org ON employment(org_unit_id);
CREATE INDEX IF NOT EXISTS idx_employment_type_status ON employment(type, status);

DROP TRIGGER IF EXISTS trg_employment_updated_at ON employment;
CREATE TRIGGER trg_employment_updated_at
BEFORE UPDATE ON employment
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Especialização: EFETIVO
CREATE TABLE IF NOT EXISTS employment_efetivo (
  employment_id UUID PRIMARY KEY REFERENCES employment(id) ON DELETE CASCADE,
  decreto_nomeacao_numero TEXT NULL,
  decreto_nomeacao_data DATE NULL,
  posse_data DATE NULL,
  exercicio_data DATE NULL,
  classe TEXT NULL,
  classe_nivel INTEGER NULL,
  estabilidade_data DATE NULL,
  estabilidade_protocolo TEXT NULL,
  estabilidade_resolucao_conjunta TEXT NULL,
  estabilidade_publicacao_data DATE NULL
);

-- Especialização: COMISSIONADO
CREATE TABLE IF NOT EXISTS employment_comissionado (
  employment_id UUID PRIMARY KEY REFERENCES employment(id) ON DELETE CASCADE,
  decreto_nomeacao_numero TEXT NULL,
  decreto_nomeacao_data DATE NULL,
  posse_data DATE NULL,
  exercicio_data DATE NULL,
  simbolo TEXT NULL,
  decreto_exoneracao_numero TEXT NULL,
  decreto_exoneracao_data DATE NULL,
  com_vinculo BOOLEAN NULL,
  funcao_exercida TEXT NULL
);

-- Especialização: ESTAGIÁRIO
CREATE TABLE IF NOT EXISTS employment_estagiario (
  employment_id UUID PRIMARY KEY REFERENCES employment(id) ON DELETE CASCADE,
  tce_numero TEXT NULL,
  tce_ano SMALLINT NULL,
  inicio_data DATE NULL,
  fim_data DATE NULL,
  aditivo_novo_fim_data DATE NULL,
  rescisao_data DATE NULL
);