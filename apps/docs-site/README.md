# Plataforma AGEPAR — documentação de desenvolvimento

Projeto Docusaurus da documentação técnica do Portal AGEPAR.

## Estado atual

- **Framework:** Docusaurus v3
- **Base URL em dev:** `/devdocs/`
- **Proxy do Host:** `http://localhost:5173/devdocs/`
- **Acesso direto opcional:** `http://localhost:9000/devdocs/`
- **Entrada principal:** `docusaurus.config.ts`
- **Navegação:** `sidebars.ts`

## Como rodar no monorepo

### Via Docker Compose
O jeito mais fiel ao repositório é subir a stack pela raiz:

```bash
./infra/scripts/dev.sh up
```

### Diretamente
Dentro de `apps/docs-site`:

```bash
npm install
npm run start -- --host 0.0.0.0 --port 8000
```

## Estrutura

```text
apps/docs-site/
  docs/                 # conteúdo em Markdown/MDX
  blog/                 # posts técnicos
  src/                  # páginas e CSS customizado
  static/               # assets
  sidebars.ts           # sidebar principal
  docusaurus.config.ts  # baseUrl, navbar, footer, temas
  package.json          # scripts do Docusaurus
```

## Leitura recomendada antes de evoluções sensíveis

Vale começar por:

- `../../IMPLEMENTACOES_FUTURAS.md`
- `docs/dev-guide.md`
- `docs/15-apêndices/05-diretrizes-para-implementações-futuras-e-pontos-sensíveis.md`
- `docs/15-apêndices/06-checklist-de-validação-para-mudanças-futuras.md`

Esses materiais resumem o estado funcional atual, os pontos sensíveis e o smoke mínimo para validar a stack após mudanças.

## Observações importantes

- O container de docs do compose usa **npm**.
- O diretório ainda possui `package-lock.json` e `pnpm-lock.yaml`; isso é uma
  divergência operacional conhecida e a documentação principal já registra o tema.
- O site assume `baseUrl: "/devdocs/"`, então qualquer proxy ou publicação deve
  respeitar esse prefixo ou ajustar o config antes do build.

## Padrão editorial da documentação

A convenção editorial adotada nesta revisão está documentada em:

- `apps/docs-site/docs/13-documentação-docusaurus/06-padrão-editorial-e-template-de-página.md`
