# Testes – API via cURL

Este documento reúne **comandos cURL** para testar rapidamente os principais endpoints do **BFF (FastAPI)**.  
Use-os como smoke tests manuais em dev/homolog/produção.

---

## 🔐 Autenticação

### Login
```bash
curl -i -c cookies.txt -X POST http://localhost:5173/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}'
````

### Sessão atual

```bash
curl -i -b cookies.txt http://localhost:5173/api/me
```

### Logout

```bash
curl -i -b cookies.txt -X POST http://localhost:5173/api/auth/logout
```

---

## 🩺 Saúde e Versão

```bash
curl -i http://localhost:5173/api/health
curl -i http://localhost:5173/api/version
```

---

## 📚 Catálogo

### Dev

```bash
curl -s http://localhost:5173/catalog/dev | jq .
```

### Prod (aplica RBAC)

```bash
curl -s -b cookies.txt http://localhost:5173/catalog/prod | jq .
```

---

## 🤖 Automações (padrão)

Troque `{slug}` por `dfd`, `form2json`, etc.

### Schema

```bash
curl -s http://localhost:5173/api/automations/{slug}/schema | jq .
```

### UI (iframe)

```bash
curl -i http://localhost:5173/api/automations/{slug}/ui
```

### Submeter

```bash
curl -i -b cookies.txt -X POST http://localhost:5173/api/automations/{slug}/submit \
  -H "Content-Type: application/json" \
  -d '{"campo":"valor"}'
```

### Listar submissões

```bash
curl -s -b cookies.txt http://localhost:5173/api/automations/{slug}/submissions | jq .
```

### Detalhar submissão

```bash
curl -s -b cookies.txt http://localhost:5173/api/automations/{slug}/submissions/1 | jq .
```

### Baixar resultado

```bash
curl -L -b cookies.txt -X POST http://localhost:5173/api/automations/{slug}/submissions/1/download -o resultado.out
```

---

## 🗄️ Banco (sanidade)

> Apenas para verificação rápida quando o BFF expõe health DB (opcional).

```bash
curl -s http://localhost:5173/api/health | jq .
```

---

## 🔎 Dicas

* `-i` mostra headers (útil para checar cookies de sessão).
* `-c cookies.txt` salva cookies; `-b cookies.txt` reutiliza.
* `jq` ajuda a visualizar JSON (`sudo apt install jq`).

---

## ⚠️ Segurança

* Não compartilhar `cookies.txt`.
* Em produção, usar HTTPS e `--cacert` se necessário.
* Não expor dados sensíveis nos comandos (histórico do shell).