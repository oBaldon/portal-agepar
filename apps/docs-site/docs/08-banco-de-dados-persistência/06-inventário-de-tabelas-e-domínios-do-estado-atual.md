---
id: inventario-de-tabelas-e-dominios-do-estado-atual
title: "Inventário de tabelas e domínios do estado atual"
sidebar_position: 6
---

O estado atual do portal combina duas fontes principais de schema:

- `infra/sql/init_db.sql` — domínio base de autenticação, RBAC, auditoria e RH;
- `apps/bff/app/db.py` — tabelas operacionais das automações e serviços do portal.

## Domínio base inicializado em `infra/sql/init_db.sql`

### Autenticação, RBAC e auditoria
- `users`
- `roles`
- `user_roles`
- `auth_sessions`
- `login_attempts`
- `audit_events`
- `app_logs`

### Estruturas organizacionais e vínculo funcional
- `org_units`
- `employment`
- `employment_efetivo`
- `employment_comissionado`
- `employment_estagiario`
- `employment_efetivo_outro_cargo`
- `user_org_units`

### Formação e histórico funcional
- `efetivo_capacitacoes`
- `efetivo_giti`
- `user_education_graduacao`
- `user_education_posgrad`

### Alertas globais
- `platform_alerts`
- `platform_alert_recipients`

## Domínio operacional garantido por `apps/bff/app/db.py`

- `submissions`
- `automation_audits`
- `fileshare_items`
- `notifications`
- `notification_recipients`
- `platform_alerts`
- `platform_alert_recipients`
- `tasks`
- `task_events`
- `task_comments`

## Observação importante

`platform_alerts` e `platform_alert_recipients` aparecem tanto na trilha de
bootstrap SQL quanto na camada operacional do BFF. A documentação deve tratar
isso como **sobreposição intencional de garantia idempotente**, e não como dois
domínios independentes.

## Implicação operacional

Como `DATABASE_URL` é obrigatória em `apps/bff/app/db.py`, o backend atual não
representa mais o cenário antigo de “subir com SQLite local sem banco externo”.
