# CLAUDE.md — aplicação `assistente` (SEI-IA)

Decisões e convenções para agentes de IA trabalhando nesta aplicação. O único
endpoint público de chat é `/llm_lang/session_stream`, registrado em
`sei_ia/main.py:159`. Os routers clássico e mini foram removidos.
RAG e benchmark permanecem intocados, incluindo suas dependências clássicas;
os runners antigos precisarão de atualização antes de novo uso.

## Decisões

### Reasoning do `session_stream`

- O padrão da aplicação é o modelo **`standard` com `effort=low`**, **independente da
  complexidade** da pergunta do usuário (não há gating do effort por easy/medium/high).
- O parâmetro `effort` é alterado para **`medium`** apenas quando o usuário solicita
  **`use_thinking=True`** no request.
- O reasoning fica **sempre ligado** (Responses API); `temperature` não é enviado e o
  proxy/modelo aplica seu default. O que muda com `use_thinking` é só o **nível** do
  effort (`low` → `medium`), não ligar/desligar.

**Onde mora:**
- `configs/settings_config.py`: `SESSION_REASONING_EFFORT` (default `low`) e
  `SESSION_REASONING_EFFORT_THINKING` (default `medium`). São settings próprios da
  sessão. O `REASONING_EFFORT` global pertence apenas à implementação legada não
  registrada.
- `agents/session_agent/agent.py` (`build_session_agent`): seleciona o effort
  (`medium` se `use_thinking`, senão `SESSION_REASONING_EFFORT`).

**Por quê (rationale):** medição e2e (ver `experimentos/latencia-session-vs-classico/`)
mostrou que `effort=off` ≈ `effort=low` em latência — o custo do resumo amplo é a
exploração agêntica multi-doc, não o reasoning. Logo, manter `low` sempre não custa
velocidade e preserva os blocos de raciocínio para o frontend; `use_thinking` sobe para
`medium` quando o usuário quer aprofundamento.
