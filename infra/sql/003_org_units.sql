-- 003_org_units.sql
-- Estrutura hierárquica de unidades organizacionais


-- Extensões necessárias (id UUID via gen_random_uuid, citext para nomes)
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;


-- Função genérica para updated_at
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- Tabela de unidades organizacionais
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
CREATE INDEX IF NOT EXISTS idx_org_units_name ON org_units(LOWER(name));


DROP TRIGGER IF EXISTS trg_org_units_updated_at ON org_units;
CREATE TRIGGER trg_org_units_updated_at
    BEFORE UPDATE ON org_units
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();