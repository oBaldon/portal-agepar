# Testes – Manuais (Guia Rápido)

Este guia reúne **roteiros manuais** para validar o Portal AGEPAR em dev/homolog.  
Use-o como checklist antes de releases.

---

## 🔐 Autenticação

1. Acessar `/login`.  
2. Informar credenciais válidas.  
3. Verificar redirecionamento para **Home**.  
4. Abrir menu de conta (se existir) e executar **Logout**.  
5. Confirmar que rotas protegidas exigem login.

---

## 📚 Catálogo & RBAC

1. Acessar `/catalog/dev` e validar JSON básico.  
2. Logar com usuário **sem** roles → Home não exibe blocos protegidos.  
3. Logar com usuário **com** roles → Home exibe blocos protegidos.  
4. Navbar exibe categorias na ordem.  
5. Breadcrumbs condizem com `navigation[]`.

---

## 🤖 Automações

1. Abrir rota de um bloco (ex.: `/compras/dfd`).  
2. Verificar carregamento da UI (iframe).  
3. Preencher dados e **submeter**.  
4. Acompanhar status (pending → processing → success).  
5. Baixar **resultado** com o endpoint `/download`.

---

## 🧭 Rotas & Navegação

1. Acessar rota inexistente → ver página **404**.  
2. Acessar rota protegida sem permissão → ver **403**.  
3. Acessar `/docs/` → documentação renderizada via proxy.  

---

## 🧪 Saúde & Observabilidade

1. `GET /api/health` → 200 OK.  
2. `GET /api/version` → versão atual do BFF.  
3. Verificar logs do BFF/Host em tempo real.  

---

## 📈 Performance (Básico)

1. Abrir DevTools → **Network**.  
2. Validar TTFB < 200ms e carregamento da Home < 2s em rede normal.  
3. Executar teste rápido com k6 (opcional).  

---

## 🛡️ Segurança (Básico)

1. Cookies com `HttpOnly`, `Secure` (em HTTPS) e `SameSite`.  
2. CSP ativa e iframes com `sandbox`.  
3. CORS restrito no BFF.  

---

## ✅ Checklist de Release

- [ ] Autenticação e RBAC funcionando.  
- [ ] Catálogo válido e visível.  
- [ ] Automações principais OK (DFD, Form2JSON).  
- [ ] Observabilidade: logs, métricas e health.  
- [ ] Backups agendados e íntegros.  
- [ ] Sem erros críticos no console do navegador.  