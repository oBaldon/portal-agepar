---
id: logging-info-error
title: "Logging (INFO/ERROR) no estado atual"
sidebar_position: 7
---

## Configuração observada

Em `apps/bff/app/main.py`:
- `logging.basicConfig(...)`
- formato simples em stdout
- `LOG_LEVEL` vindo de env
- logs de startup já registram:
  - `ENV`
  - `AUTH_MODE`
  - `AUTH_LEGACY_MOCK`
  - `LOG_LEVEL`
  - `EP_MODE`
  - `CORS_ORIGINS`
  - `CATALOG_FILE`

## Eventos úteis já logados
- startup do BFF
- inicialização do banco
- versões de motores DFD, Férias, ETP, Tasks e Avisos
- falhas ao garantir colunas de férias
- fluxos internos de módulos específicos

## Limitação real do estado atual

O projeto ainda usa muitos `except Exception`, o que reduz a precisão do logging
em vários fluxos. A documentação registra isso como dívida técnica real, não
como um padrão já resolvido.
