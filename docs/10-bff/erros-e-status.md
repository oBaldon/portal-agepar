# Erros e Status no BFF

O **BFF (FastAPI)** do Portal AGEPAR adota um padrão consistente para **erros e códigos de status HTTP**, garantindo mensagens claras e rastreabilidade para usuários e desenvolvedores.

---

## 📑 Objetivos

- **Uniformizar respostas de erro** em todo o backend.  
- Garantir **códigos HTTP corretos** para cada tipo de falha.  
- Retornar **mensagens úteis e seguras** (sem vazar dados sensíveis).  
- Facilitar **debug** e auditoria via logs e tabela `audits`.  

---

## 📊 Padrões de Resposta

### 🔹 Sucesso
```json
{
  "status": "success",
  "data": { ... }
}
````

### 🔹 Erro

```json
{
  "status": "error",
  "code": 400,
  "message": "Descrição do erro",
  "details": { ... }   // opcional
}
```

---

## 📌 Códigos e Significados

| Código                        | Situação                             | Exemplo                                  |
| ----------------------------- | ------------------------------------ | ---------------------------------------- |
| **200 OK**                    | Operação bem-sucedida                | Consulta de submissões                   |
| **201 Created**               | Recurso criado com sucesso           | Nova submissão de automação              |
| **204 No Content**            | Operação sem retorno                 | Logout de sessão                         |
| **400 Bad Request**           | Entrada inválida / payload incorreto | Campo obrigatório ausente                |
| **401 Unauthorized**          | Usuário não autenticado              | Tentativa de acessar `/api/me` sem login |
| **403 Forbidden**             | Usuário sem permissão (RBAC)         | Acesso a bloco restrito                  |
| **404 Not Found**             | Recurso inexistente                  | Submissão com ID inválido                |
| **409 Conflict**              | Conflito de estado                   | Submissão duplicada                      |
| **422 Unprocessable Entity**  | Validação Pydantic falhou            | Campo fora do formato esperado           |
| **500 Internal Server Error** | Erro inesperado no servidor          | Falha de banco de dados                  |

---

## 🧩 Exemplos

### 400 – Requisição inválida

```json
{
  "status": "error",
  "code": 400,
  "message": "Campo obrigatório 'nome' não informado"
}
```

### 401 – Não autenticado

```json
{
  "status": "error",
  "code": 401,
  "message": "Sessão inválida ou expirada"
}
```

### 403 – Sem permissão

```json
{
  "status": "error",
  "code": 403,
  "message": "Você não possui permissão para acessar este recurso"
}
```

### 422 – Validação

```json
{
  "status": "error",
  "code": 422,
  "message": "Erro de validação",
  "details": {
    "campo": "email",
    "erro": "Formato inválido"
  }
}
```

---

## 🔐 Segurança das Mensagens

* **Não incluir dados sensíveis** (tokens, senhas, dados pessoais).
* **Contexto suficiente** para depuração, mas genérico para usuários finais.
* Erros detalhados ficam em **logs internos**, não na resposta ao cliente.

---

## 🚀 Próximos Passos

* Criar **middleware global de erros** no FastAPI para unificar tratamento.
* Implementar testes automáticos para validar **respostas de erro esperadas**.
* Integrar auditoria (`audits`) com eventos de erro relevantes.

---

📖 **Próximo passo:** [API – Health & Version](api/health-version.md)

