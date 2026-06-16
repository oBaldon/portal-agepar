---
id: testes-de-api-curl-pytest-e-exemplos
title: "Testes de API (cURL) e lacuna atual de pytest"
sidebar_position: 1
---

## O que existe hoje
- smoke tests via `curl`
- testes manuais guiados
- nenhuma suíte `pytest` versionada no repositório

## Smoke tests úteis

### Saúde e versão
```bash
curl -i http://localhost:8000/health
curl -s http://localhost:8000/version | jq .
```

### Catálogo
```bash
curl -s http://localhost:8000/catalog/dev | jq .
```

### Auth
```bash
curl -i -X POST http://localhost:8000/api/auth/login   -H 'Content-Type: application/json'   -d '{"identifier":"dev@example.com","password":"dev"}'
```

> O resultado do login depende do modo efetivo de auth do ambiente.

## Como a documentação passa a tratar pytest

Antes, a documentação sugeria pytest quase como se já existisse uma base pronta.
Agora ela registra o estado real: o repositório ainda **não tem** suíte
automatizada, apenas um espaço claro para introduzi-la.
