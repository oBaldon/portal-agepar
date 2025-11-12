-- 006_seeds_org_units.sql (revisado)
-- Semeadura de unidades organizacionais (raiz, filhas e netas)

BEGIN;

-- 1) Raiz
INSERT INTO org_units(code, name, parent_id)
VALUES ('AGEPAR','AGEPAR', NULL)
ON CONFLICT (code) DO NOTHING;

-- 2) Filhas diretas da raiz
INSERT INTO org_units(code, name, parent_id)
SELECT v.code, v.name, p.id
FROM (VALUES
  ('AGEPAR-GOV','Governança'),
  ('AGEPAR-TI','Tecnologia da Informação')
) AS v(code, name)
JOIN org_units p ON p.code = 'AGEPAR'
LEFT JOIN org_units u ON u.code = v.code
WHERE u.id IS NULL;

-- 3) Netas (dependem das filhas acima)
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
