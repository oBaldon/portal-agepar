---
id: sem-segredos-no-repo
title: "Segredos no repositório: regra e estado atual"
sidebar_position: 3
---

## Regra

Nenhum segredo real deveria estar versionado.

## Estado atual observado

Neste snapshot, o `.env.example` já foi sanitizado e usa placeholders vazios para
integrações externas, como o Expresso.

Isso melhora bastante a situação em relação a revisões anteriores, mas **não**
transforma `.env.example` em fonte de verdade para produção.

## Como interpretar corretamente o repo

- `SESSION_SECRET=dev-secret` é um placeholder de laboratório;
- `PGPASSWORD=portaldev` é um default de dev;
- `EXPRESSO_API_USER` e `EXPRESSO_API_PASSWORD` vazios indicam que o segredo deve ser preenchido fora do versionamento;
- qualquer ambiente real continua precisando de secret manager, variável protegida
  ou mecanismo equivalente.

## O que a documentação registra

1. o padrão correto continua sendo “segredos via ambiente/secret manager”;
2. o snapshot atual já está sanitizado no que diz respeito ao `.env.example`;
3. defaults de desenvolvimento não devem ser promovidos automaticamente para
   ambientes reais.
