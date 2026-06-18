---
id: "modelagem-emails-usuario-pendencia"
title: "Pendência de modelagem dos e-mails de usuário"
sidebar_position: 11
---

# Pendência de modelagem dos e-mails de usuário

## Objetivo desta página

Registrar com precisão uma dívida técnica já identificada no Portal AGEPAR:

- **o que o sistema faz hoje** com `users.email` e `users.email_institucional`;
- **o que a regra de negócio deseja** para “e-mail institucional” e “e-mail secundário”;
- **por que uma troca ingênua de nomes/rótulos quebra outros pontos do código**;
- **qual estratégia é mais segura** para resolver isso no futuro.

Esta página existe para evitar uma correção apressada que quebre login, envio de e-mail,
cadastro de usuários, autocomplete do ETP e contratos já consumidos pelas UIs
embutidas.

---

## Resumo executivo

Hoje o sistema está, na prática, acoplado a `users.email` como endereço canônico do usuário.

Esse campo participa de:

- login local e identificação por e-mail;
- sessão autenticada (`request.session["user"]["email"]`);
- envio de notificações por e-mail;
- vários contratos de API e telas de perfil/usuários.

Ao mesmo tempo, o negócio deseja que:

- o endereço `@agepar.pr.gov.br` seja tratado como **e-mail institucional**;
- o outro endereço (por exemplo, Gmail pessoal) seja tratado como **e-mail secundário**.

O problema é que o nome atual das colunas e dos campos expostos na API/UI induz a um
entendimento ambíguo:

- `users.email` é mostrado/entendido em vários pontos como “e-mail principal”;
- `users.email_institucional` é mostrado/entendido em vários pontos como “e-mail institucional”.

No uso operacional desejado, porém, o e-mail usado para login e para integração oficial
do portal deveria ser justamente o institucional.

---

## Estado atual observado no código

### Colunas físicas do banco

No domínio `users`, o schema atual mantém:

- `users.email`
- `users.email_institucional`

Neste snapshot não existe coluna física `email_secundario`.

### Comportamento real do sistema

Hoje o sistema usa `users.email` como o endereço “canônico” em partes críticas:

- **Auth**: login por e-mail consulta `users.email`;
- **Sessão**: o objeto da sessão mantém `user.email`;
- **Cadastro/edição de usuários**: `email_principal` mapeia para `users.email`;
- **Perfil self-service**: `email_principal` mapeia para `users.email`;
- **Notificações**: o envio tenta `email` primeiro e só usa `email_institucional` como fallback;
- **Busca de usuários no ETP**: o autocomplete hoje prioriza `email_institucional` na exibição.

### Semântica operacional resultante

Na prática, o sistema atual está mais próximo de:

- `users.email` = “e-mail operacional principal do sistema”
- `users.email_institucional` = “e-mail alternativo / complementar”

Essa semântica funcional **não coincide necessariamente** com a nomenclatura desejada pelo negócio.

---

## Regra de negócio desejada

A regra pretendida é:

- `users.email` deve representar o **e-mail institucional**;
- `users.email_institucional` deve deixar de ser entendido como “institucional” e passar a representar um **e-mail secundário**;
- a camada de API/UI deve expor isso com nomes claros, por exemplo:
  - `email_institucional` → mapeando para `users.email`
  - `email_secundario` → mapeando para `users.email_institucional`

Em linguagem de produto:

- o login deve ocorrer com o e-mail institucional;
- o e-mail institucional deve ser o endereço oficial do usuário no portal;
- o e-mail secundário pode ser Gmail ou outro endereço pessoal/complementar;
- o e-mail secundário **não deve ser tratado como identidade canônica** por padrão.

---

## Por que “só trocar os nomes” não basta

Uma troca puramente cosmética de rótulo ou uma inversão rápida de significado quebra
ou confunde várias partes do sistema.

### 1) Login e sessão

O módulo de auth consulta `users.email` como identificador por e-mail.

Isso significa que:

- se alguém tentar migrar a semântica sem preservar `users.email` como o campo do login,
  o login local pode parar de funcionar;
- se alguém trocar os nomes na UI, mas não alinhar a API, o usuário verá “e-mail institucional”
  na tela enquanto o backend continua tratando aquilo como `email_principal`.

### 2) Notificações e envio via Expresso

O envio de e-mail em `apps/bff/app/notifications.py` faz:

1. tenta `email`;
2. se `email` for inválido ou ausente, tenta `email_institucional`.

Ou seja, o comportamento real atual é: **`email` é preferencial; `email_institucional` é fallback**.

Se a semântica desejada passar a ser “`users.email_institucional` é e-mail secundário”,
então manter essa regra sem revisão faz o sistema cair para um e-mail pessoal/complementar
em notificações oficiais.

Isso é especialmente sensível para:

- notificações inbox com e-mail complementar;
- relatórios/avisos enviados a partir de rotinas administrativas;
- qualquer fluxo que hoje dependa da integração com o Expresso.

### 3) Perfil e cadastro de usuários

Nos módulos `profile.py` e `usuarios.py`, os contratos atuais ainda usam nomes como:

- `email_principal`
- `email_institucional`

Esses contratos mapeiam diretamente para:

- `email_principal` → `users.email`
- `email_institucional` → `users.email_institucional`

Se a semântica mudar no negócio e os contratos não acompanharem, a API passa a “mentir”:

- o campo chamado `email_institucional` deixará de ser o institucional de fato;
- o campo chamado `email_principal` continuará existindo, mas sem clareza de significado.

### 4) Busca/autocomplete do ETP

No snapshot atual, a busca de usuários no ETP usa:

```sql
COALESCE(email_institucional::text, email::text, '') AS email
```

Na prática, isso prioriza `users.email_institucional` ao montar o e-mail exibido na busca.

Se `users.email_institucional` passar a significar “e-mail secundário”, a busca continuará
mostrando primeiro o endereço menos canônico, o que aumenta ruído para quem usa a tela.

---

## Áreas afetadas pela pendência

Os pontos que dependem dessa modelagem hoje incluem:

- auth/login local;
- sessão autenticada e serialização do usuário;
- `notifications.py`;
- integração com Expresso;
- automação de perfil (`profile.py`);
- automação de usuários (`usuarios.py`);
- autocomplete e seleção de usuários no ETP;
- templates HTML/JS embutidos do profile e usuários;
- documentação técnica do BFF e fluxos relacionados.

Isso significa que a correção futura deve ser tratada como ajuste transversal de contrato,
e não como simples rename local.

---

## Estratégia mais segura para resolver no futuro

A abordagem mais segura não é trocar nomes de forma abrupta. O caminho recomendado é:

1. **definir a semântica canônica desejada** em nível de produto e backend;
2. **preservar `users.email` como campo canônico de login** durante a transição;
3. **ajustar os contratos de API/UI** para nomes semanticamente corretos;
4. **revisar a política de seleção de e-mail** nas notificações;
5. **corrigir autocomplete, telas e documentação** no mesmo pacote;
6. **migrar dados existentes**, se necessário, com critério explícito.

Na prática, a transição futura tende a envolver:

- compatibilidade temporária entre nomes antigos e novos;
- revisão de validações e labels das UIs;
- revisão de consultas SQL e serialização JSON;
- testes manuais focados em login, perfil, usuários, ETP e notificações.

---

## O que esta página decide e o que ela não decide

Esta página **decide** apenas registrar a pendência e tornar a documentação coerente com o
comportamento real atual.

Esta página **não decide**, por si só:

- renome de coluna no banco;
- migração de dados;
- mudança imediata de payloads;
- troca da política atual de fallback em notificações;
- revisão do fluxo de login.

Essas mudanças exigem trabalho coordenado de implementação e validação.

---

## Conclusão

Hoje, o Portal AGEPAR funciona com uma semântica técnica em que `users.email` é o campo
mais canônico do sistema, mesmo que os nomes expostos em partes da UI sugiram outra leitura.

A dívida técnica não está apenas em “nomes ruins”, mas no fato de que **auth, sessão,
notificação, perfil, usuários e ETP já dependem desses nomes e mapeamentos**.

Por isso, a correção segura precisa ser tratada como um refactor de contrato e de domínio,
não como ajuste cosmético isolado.
