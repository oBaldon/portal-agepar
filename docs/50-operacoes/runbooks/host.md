# Runbook – Host (React + Vite)

Este runbook cobre procedimentos de operação, diagnóstico e recuperação do **Host** do Portal AGEPAR.

---

## 🎯 Objetivo

- Garantir disponibilidade da interface web.  
- Fornecer passos claros para lidar com falhas no Host.  
- Minimizar tempo de indisponibilidade em incidentes.  

---

## 🛠️ Health Check

- Acessar `http://localhost:5173/` (dev) ou `https://portal.agepar.gov.br/` (prod).  
- Esperado: carregamento da **Home Dashboard**.  

Endpoints auxiliares:
- `/api/health` (via proxy para BFF).  
- `/catalog/dev` ou `/catalog/prod` (carregamento do catálogo).  
- `/docs/` (proxy para MkDocs).  

---

## 📂 Logs

- Em dev:
  ```bash
  docker compose logs host
````

* Em prod: logs coletados no proxy reverso (Nginx/Traefik) e no serviço Node/Vite.

---

## 🚦 Problemas Comuns

### Página em branco

1. Abrir console → verificar erros JS.
2. Confirmar build (`npm run build` no Host).
3. Validar se catálogo foi carregado (`/catalog/dev`).

### Erro de proxy API

1. Checar se serviço BFF está rodando (`docker compose ps bff`).
2. Validar configuração de proxy (`vite.config.ts`).

### Navbar vazia

1. Verificar se catálogo tem categorias/blocos.
2. Validar roles do usuário logado (RBAC no front).

---

## ♻️ Restart Seguro

```bash
docker compose restart host
```

Em produção:

```bash
ssh deploy@host "cd portal-agepar && docker compose pull host && docker compose up -d host"
```

---

## 🧪 Testes Pós-Restart

* `http://localhost:5173/` carrega Home.
* Navbar exibe categorias.
* Blocos acessíveis respeitam RBAC.
* `/docs/` disponível.

---

## 🚨 Escalonamento

* Se Host indisponível mas BFF ok → provável erro de build/deploy → revisar CI/CD.
* Se Host carrega mas catálogo vazio → escalar para equipe **BFF**.
* Problemas de UX ou rendering → encaminhar para equipe **Frontend**.

---

## 🔮 Futuro

* Monitoramento de Web Vitals (LCP, CLS, FID) via observabilidade.
* Deploy com **rollback automático** em caso de falha.
* CDN para distribuição de assets estáticos do Host.
