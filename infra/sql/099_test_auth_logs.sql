-- Smoke test automatizado do schema de autenticação/logs.
-- Executar com psql; o script é idempotente e limpa seus artefatos.

-- Helper de assert
CREATE OR REPLACE FUNCTION assert_true(cond boolean, msg text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  IF NOT cond THEN
    RAISE EXCEPTION 'ASSERTION FAILED: %', msg;
  END IF;
END; $$;

DO $$
DECLARE
  test_email text := 'tester_' || substr(gen_random_uuid()::text, 1, 8) || '@Example.com';
  u_id uuid;
  sess_count int;
  audits_count int;
  logs_count int;
  dup_blocked boolean := false;
BEGIN
  -- 1) Criar usuário de teste (email CITEXT)
  INSERT INTO users (name, email, status, source, attrs)
  VALUES ('Tester User', test_email, 'active', 'local', jsonb_build_object('origin','099_test'))
  RETURNING id INTO u_id;

  PERFORM assert_true(u_id IS NOT NULL, 'user id must be set');

  -- 2) Tentar duplicar com caixa diferente (CITEXT → deve falhar em uq)
  BEGIN
    INSERT INTO users (name, email, status, source)
    VALUES ('Dup User', upper(test_email), 'active', 'local');
  EXCEPTION WHEN unique_violation THEN
    dup_blocked := true;
  END;

  PERFORM assert_true(dup_blocked, 'duplicate email (CITEXT) was not blocked');

  -- 3) Criar sessão (sem RETURNING)
  INSERT INTO auth_sessions (user_id, expires_at, ip, user_agent)
  VALUES (u_id, now() + interval '1 hour', '127.0.0.1', 'psql/smoke');

  SELECT count(*) INTO sess_count FROM auth_sessions WHERE user_id = u_id;
  PERFORM assert_true(sess_count = 1, format('expected 1 session, got %s', sess_count));

  -- 4) Registrar tentativas de login
  INSERT INTO login_attempts (user_id, login_identifier, success, reason, ip, user_agent)
  VALUES
    (u_id, test_email, true,  'ok',          '127.0.0.1', 'psql/smoke'),
    (u_id, test_email, false, 'bad_password','127.0.0.1', 'psql/smoke');

  -- 5) Auditoria
  INSERT INTO audit_events (actor_user_id, action, object_type, object_id, message, metadata, ip, user_agent)
  VALUES (u_id, 'auth.login', 'user', u_id::text, 'Login de teste', jsonb_build_object('smoke', true), '127.0.0.1', 'psql/smoke');

  SELECT count(*) INTO audits_count
  FROM audits
  WHERE action = 'auth.login' AND object_id = u_id::text;
  PERFORM assert_true(audits_count = 1, format('expected 1 audit, got %s', audits_count));

  -- 6) Logs de aplicação
  INSERT INTO app_logs (level, logger, message, context, user_id)
  VALUES ('INFO', 'smoke.test', 'Teste de log', jsonb_build_object('k','v'), u_id);

  SELECT count(*) INTO logs_count
  FROM app_logs
  WHERE logger = 'smoke.test' AND user_id = u_id;
  PERFORM assert_true(logs_count = 1, format('expected 1 app_log, got %s', logs_count));

  RAISE NOTICE 'ALL TESTS PASSED (user=% email=%)', u_id, test_email;

  -- Limpeza: remover artefatos deste teste
  DELETE FROM app_logs      WHERE user_id = u_id;
  DELETE FROM audit_events  WHERE actor_user_id = u_id;
  DELETE FROM auth_sessions WHERE user_id = u_id;
  UPDATE login_attempts SET user_id = NULL WHERE user_id = u_id;
  DELETE FROM users WHERE id = u_id;
END $$;

-- limpeza do helper
DROP FUNCTION IF EXISTS assert_true(boolean, text);
