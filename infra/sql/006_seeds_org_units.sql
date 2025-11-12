-- 006_seeds_org_units.sql
-- Semeadura de unidades organizacionais (mínimo útil)

WITH roots AS (
  INSERT INTO org_units(code, name, parent_id)
  VALUES ('AGEPAR','AGEPAR', NULL)
  ON CONFLICT (code) DO NOTHING
  RETURNING id, code
), gov AS (
  INSERT INTO org_units(code, name, parent_id)
  SELECT 'AGEPAR-GOV','Governança', ou.id FROM org_units ou WHERE ou.code='AGEPAR'
  ON CONFLICT (code) DO NOTHING
  RETURNING id
), dti AS (
  INSERT INTO org_units(code, name, parent_id)
  SELECT 'AGEPAR-DTI','Diretoria de TI', ou.id FROM org_units ou WHERE ou.code='AGEPAR'
  ON CONFLICT (code) DO NOTHING
  RETURNING id
)
INSERT INTO org_units(code, name, parent_id)
SELECT x.code, x.name, p.id
FROM (
  VALUES
    ('GOV-RH','Recursos Humanos','AGEPAR-GOV'),
    ('GOV-COMPRAS','Compras & Contratos','AGEPAR-GOV'),
    ('GOV-JUR','Jurídico','AGEPAR-GOV'),
    ('GOV-OUV','Ouvidoria','AGEPAR-GOV'),
    ('DTI-DEV','Desenvolvimento','AGEPAR-DTI'),
    ('DTI-INFRA','Infraestrutura','AGEPAR-DTI')
) AS x(code,name,parent_code)
JOIN org_units p ON p.code = x.parent_code
ON CONFLICT (code) DO NOTHING;