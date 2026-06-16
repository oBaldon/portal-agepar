---
id: padrao-editorial-e-template-de-pagina
title: "Padrão editorial e template de página"
sidebar_position: 6
---

Esta página consolida o padrão editorial usado para revisar a documentação do
portal e corrige a deriva entre arquivos antigos e arquivos novos.

## Frontmatter mínimo

Toda página nova deve começar com:

```md title="template mínimo"
---
id: identificador-unico-da-pagina
title: "Título exibido na navegação"
sidebar_position: 1
---
```

### Regras
- `id` deve ser **único no site inteiro**;
- `title` deve refletir o comportamento real, não intenção antiga;
- `sidebar_position` é obrigatório para páginas ordenadas dentro da seção.

## Estrutura recomendada do conteúdo

Quando fizer sentido, use esta sequência:

1. **Objetivo**
2. **Estado atual implementado**
3. **Arquivos mapeados**
4. **Passivos / observações**
5. **Próximos passos** ou **Leitura relacionada**

Nem toda página precisa de todas as seções, mas páginas novas não devem nascer
sem contexto mínimo do estado real.

## Convenções de links

- Prefira links relativos como `./arquivo` e `../outra-secao/arquivo`;
- evite hardcode de rotas absolutas `/docs/...`, porque o site usa
  `baseUrl: "/devdocs/"`;
- quando precisar citar rota pública da documentação, prefira escrever
  `/devdocs/...` explicitamente no texto.

## Convenções para arquivos históricos

Alguns arquivos mantêm nomes herdados por compatibilidade. Nesses casos:

```md title="nota curta de arquivo histórico"
> O nome do arquivo é histórico. O conteúdo abaixo foi atualizado para o estado atual.
```

Essa nota deve aparecer logo após o frontmatter.

## O que esta revisão corrigiu

- IDs duplicados em páginas `index.md`;
- páginas sem `frontmatter` completo;
- links relativos quebrados entre documentos;
- snippets ainda apontando para `/docs` como se fosse a base pública atual;
- arquivos novos fora do padrão editorial mínimo.
