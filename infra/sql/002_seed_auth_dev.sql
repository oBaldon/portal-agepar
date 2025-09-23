-- Seeds de desenvolvimento para autenticação/RBAC

-- Roles padrão
INSERT INTO roles (name, description)
VALUES 
  ('admin', 'Acesso administrativo')
  --('viewer', 'Leitura'),
  --('compras', 'Processos de compras')
ON CONFLICT (name) DO NOTHING;

-- Usuário dev (email local sem senha; servirá para RBAC e testes manuais depois)
WITH upsert AS (
  INSERT INTO users (name, email, status, source, is_superuser, attrs)
  VALUES ('Dev Admin', 'dev@local', 'active', 'local', TRUE, '{"seed": true}')
  -- Índice único é PARCIAL (email IS NOT NULL), então declarar o predicado:
  ON CONFLICT (email) WHERE email IS NOT NULL DO UPDATE SET
    name = EXCLUDED.name,
    status = EXCLUDED.status,
    source = EXCLUDED.source,
    is_superuser = EXCLUDED.is_superuser,
    attrs = EXCLUDED.attrs
  RETURNING id
)
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM upsert u
JOIN roles r ON r.name IN ('admin')--, 'viewer', 'compras')
ON CONFLICT DO NOTHING;
-- Nota: senha não é necessária para source='local' se for superuser