---
id: fluxo-dev-local-vs-produção
title: "Fluxo dev local vs. produção"
sidebar_position: 4
---

## Desenvolvimento local

O fluxo de dev mais fiel ao repositório atual é:

```bash
cp .env.example .env
./infra/scripts/dev.sh up
```

Isso sobe:
- Host
- BFF
- Docs
- Postgres

### Características do dev atual
- Host com Vite em `:5173`
- BFF em `:8000`
- Docs em `/devdocs/`
- Postgres em `:5432`
- compose com volumes montados e hot reload
- auth variável entre `local` e `mock`, conforme como a stack foi iniciada

## Execução local sem Docker

Também é possível, mas exige cuidado com as portas e com o banco:

- BFF:
  ```bash
  cd apps/bff
  DATABASE_URL=postgresql://portal:portaldev@localhost:5432/portal ./run_dev.sh
  ```

- Host:
  ```bash
  cd apps/host
  npm install
  npm run dev
  ```

- Docs:
  ```bash
  cd apps/docs-site
  npm install
  npm run start -- --host 0.0.0.0 --port 8000
  ```

## Produção

O repositório não traz uma pipeline CI/CD consolidada, mas o desenho implícito é:

- BFF em container;
- Host buildado estaticamente;
- Docs buildadas estaticamente;
- Postgres externo/gerenciado;
- TLS e reverse proxy fora do monorepo.

## Diferenças importantes entre dev e produção

- `https_only=False` no cookie é aceitável em dev, não em produção;
- placeholders de `.env.example` não dispensam o preenchimento de segredos reais por ambiente;
- docs podem continuar em `/devdocs/` ou migrar para outro path, desde que
  `baseUrl` seja ajustado no Docusaurus;
- qualquer dependência do modo mock deve ser explicitamente desligada.
