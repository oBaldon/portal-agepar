-- 007_seed_role_rh.sql
-- Garante a role 'rh'
INSERT INTO roles(name)
SELECT 'rh'
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name='rh');