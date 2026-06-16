---
id: mapeamento-de-erros-400422
title: "Mapeamento de erros (400–422 e demais respostas)"
sidebar_position: 6
---

## O que o código faz hoje

O BFF usa uma mistura de:
- `HTTPException`
- respostas JSON específicas por módulo
- validação Pydantic/FastAPI
- muitos `except Exception` com mensagem útil ou genérica, dependendo do ponto

## Status recorrentes no repositório

- `400` → regra de negócio / input inválido
- `401` → não autenticado / sessão inválida
- `403` → sem papel suficiente / senha precisa ser trocada
- `404` → item ou recurso inexistente
- `409` → conflito de estado / duplicidade
- `422` → validação de request
- `500` → erro interno

## Leitura honesta do estado atual

Ainda não existe um único envelope global de erro aplicado de forma uniforme em
todo o BFF. A documentação, portanto, deixa de fingir essa uniformidade e passa
a registrar o padrão real: consistência parcial, mas não total.

## Recomendação prática para novos módulos

- usar mensagens curtas e legíveis;
- diferenciar `400` de `422`;
- incluir contexto em logs;
- evitar `except Exception` sem contexto;
- manter o Host preparado para lidar com envelopes variados `{detail: ...}` e
  JSONs customizados.
