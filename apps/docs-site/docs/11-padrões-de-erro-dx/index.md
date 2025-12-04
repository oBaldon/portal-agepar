---
id: index
title: "Padrões de Erro & DX"
sidebar_position: 0
---

Esta seção reúne os **padrões de erro** do Portal AGEPAR e como eles impactam a **DX** (Developer Experience) no dia a dia:

- contratos de erro padronizados (status + JSON),
- exemplos reais de 4xx/5xx nas automations (DFD, Férias),
- regras de normalização para reduzir `422`,
- guia de bolso para criar novos endpoints mantendo tudo consistente.

## Objetivos
- Descrever o **contrato de erro** adotado nas automations:
  - status HTTP coerente com o cenário (400/403/404/409/410/422/500…),
  - corpo JSON padronizado (`code`, `message`, `details`, `hint`).
- Apresentar **exemplos concretos** de 4xx/5xx:
  - payload inválido, acesso negado, recurso não encontrado,
  - falhas internas e erros de integração.
- Consolidar as **regras de normalização** (Pydantic + helpers) para evitar `422` “bobos”:
  - `populate_by_name`, `extra="ignore"`, saneamento de campos no BFF/Host.
- Definir **boas práticas** para novos endpoints:
  - como estruturar erros, logs e auditoria,
  - como manter compatibilidade com o Host (React) e com automations existentes.

## Sumário Rápido
- `01-contratos-de-erro-códigos-e-mensagens` — define o formato padrão de erros (status + JSON) e mostra o contrato usado por DFD/Férias.
- `02-exemplos-de-4xx-5xx-por-cenário` — coleções de exemplos reais de respostas 4xx/5xx com cURLs e trechos de resposta.
- `03-regras-de-normalização-para-evitar-422` — como modelos Pydantic e helpers de normalização deixam o BFF mais tolerante.
- `04-boas-práticas-para-novos-endpoints` — checklist para criar endpoints consistentes, seguros e fáceis de usar.
- `99-referencias.mdx` — mapa dos arquivos do repositório relacionados a tratamento de erros (DFD, Férias, etc.).

## Visão geral dos contratos de erro

Os contratos de erro seguem algumas regras simples:

- **Status HTTP** reflete a causa:
  - 4xx → problema no pedido/permissão (DX),
  - 5xx → problema interno (infra/BFF).
- **Corpo JSON padronizado**, por exemplo:

  ```json
  {
    "code": "validation_error",
    "message": "Há erros de validação no formulário.",
    "details": { "...": "..." },
    "hint": "Corrija os campos indicados e tente novamente."
  }
    ```

* Helpers como `err_json(...)` e formatadores de `ValidationError` garantem:

  * mensagens previsíveis,
  * campos sempre presentes,
  * facilidade para o Host exibir feedback amigável.

## Normalização para evitar 422

Para evitar `422 Unprocessable Entity` por detalhes triviais:

* modelos de entrada usam `ConfigDict(populate_by_name=True, extra="ignore")`;
* diferenças de nome (`pcaAno` vs `pca_ano`) são tratadas via `alias` em Pydantic;
* campos extras no payload são ignorados, não quebram o endpoint;
* o Host também faz pequenos ajustes (trim, tipos corretos) antes de enviar.

Resultado: menos 422 “chatos” e mais erros realmente úteis (400/403/409/422 com mensagem clara).

## Boas práticas para novos endpoints

Novos endpoints/automations devem:

* seguir o **mesmo contrato de erro** de DFD/Férias;
* usar Pydantic para validar e normalizar entrada;
* mapear erros previsíveis para 4xx e deixar 5xx só para casos realmente inesperados;
* logar e auditar erros importantes com contexto (usuário, automação, submission);
* manter respostas previsíveis para o Host (estrutura estável, campos documentados).

## Troubleshooting

* **O endpoint está devolvendo 500 genérico para erro de usuário**

  * Revise as regras de mapeamento e use 4xx (400/403/404/409/422) com JSON padronizado.
* **Muitos 422 por campo faltando ou nome trocado**

  * Adicione `alias` nos modelos Pydantic e use `populate_by_name=True` + `extra="ignore"`.
* **O frontend não sabe como exibir a mensagem de erro**

  * Garanta que o JSON contenha pelo menos `code` e `message`, e use `hint` para instruções ao usuário.
* **Novo endpoint com DX diferente das automations**

  * Use a página de “Boas práticas para novos endpoints” como checklist antes de fechar o PR.

---

> _Criado em 2025-12-04_
