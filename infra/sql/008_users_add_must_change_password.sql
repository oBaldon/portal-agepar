-- 008_users_add_must_change_password.sql
-- Adiciona flag para forçar troca de senha após cadastro/reset
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT TRUE;