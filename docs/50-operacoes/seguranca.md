# Operações – Segurança

Este documento define práticas de **segurança operacional** aplicadas ao Portal AGEPAR, cobrindo autenticação, RBAC, rede, dados e processos de resposta a incidentes.

---

## 🎯 Objetivos

- Garantir **confidencialidade, integridade e disponibilidade** do sistema.  
- Minimizar risco de acessos não autorizados.  
- Atender a requisitos de auditoria e conformidade.  

---

## 🔑 Autenticação e Sessões

- Login via `/api/auth/login` com **cookies HttpOnly**.  
- Cookies configurados com:
  - `Secure` em produção (HTTPS).  
  - `SameSite=Strict`.  
  - Tempo de expiração configurado.  
- Logout explícito com `/api/auth/logout`.  
- Sessões ativas armazenadas no banco (futuro) → suporte a múltiplos dispositivos.  

---

## 👤 Controle de Acesso (RBAC)

- Definido em nível de **bloco do catálogo** (`requiredRoles`).  
- Frontend aplica filtro (UI), mas BFF reforça no backend.  
- Qualquer requisição a `/api/automations/...` valida roles do usuário autenticado.  
- Logs de acesso negado registrados na tabela **audits**.  

---

## 🌐 Rede e Infra

- **Reverse proxy (Nginx/Traefik)** aplica TLS obrigatório.  
- Firewalls restritos:
  - Apenas Host exposto publicamente (porta 443).  
  - BFF, Docs e DB não expostos externamente.  
- Banco de dados acessível apenas via rede interna.  
- Suporte a **VPN corporativa** para acessos administrativos.  

---

## 🔐 Proteção de Dados

- Senhas e secrets nunca versionados.  
- Uso de **Vault/Secret Manager** para gestão de chaves.  
- Dados sensíveis (ex.: auditorias) criptografados em repouso.  
- Backups criptografados (AES256, SSE-KMS).  

---

## 🛡️ Boas Práticas de Código

- Validação de entrada com **Pydantic v2** no BFF.  
- Respostas de erro padronizadas (400, 401, 403, 404, 409, 422).  
- Prevenção de injeção SQL com ORM (SQLAlchemy).  
- Iframes sandboxed no Host:
  ```html
  <iframe src="/api/automations/dfd/ui" sandbox="allow-forms allow-scripts allow-same-origin" />
````

---

## 🧪 Testes de Segurança

* Testes automatizados com **OWASP ZAP** ou **Nuclei** em homolog.
* Verificação de dependências vulneráveis (npm audit, pip-audit).
* Revisão de roles em cada novo bloco do catálogo.

---

## 🚨 Resposta a Incidentes

1. **Detecção**: alertas de falha de login em massa, erros 500 anormais, tráfego suspeito.
2. **Contenção**: bloqueio temporário de IPs (WAF).
3. **Erradicação**: correção de vulnerabilidade, patch de dependência.
4. **Recuperação**: restore de backups, validação de integridade.
5. **Lições aprendidas**: relatório pós-incidente em até 48h.

---

## 🔮 Futuro

* MFA (autenticação multifator) para usuários administrativos.
* Integração com **SIEM corporativo**.
* Logs de auditoria assinados digitalmente.
* Rotação automática de segredos via Vault.