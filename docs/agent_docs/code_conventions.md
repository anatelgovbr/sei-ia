# Code conventions

> **Nota:** este arquivo vai para o mirror externo público — não incluir hostnames, servidores ou variáveis internas.

Convenções que seguimos ao escrever código. **Estilo é enforçado por ferramenta, não por você** — rode Ruff e os hooks de pre-commit; não reaplique regra à mão (agente não faz trabalho de linter). O que **bloqueia merge** está em `running_tests.md`; layout de pastas e responsabilidade de cada módulo estão em `service_architecture.md`.

> **Escopo.** O monorepo tem 3 apps com maturidade diferente. Cada convenção abaixo está marcada como **comum ao monorepo** ou **por app**. `assistente` é a app canônica e a mais madura; várias convenções existem só nela.

## Ferramentas e enforcement

- **Ruff** é o linter + formatter de **todas** as apps. Rode-o; não reaplique à mão. Pin `ruff==0.14.10` (CI). O conjunto de regras (`[tool.ruff.lint]`) é **por app** (ver "Divergências por app"). Config do `assistente`: `aplicacoes/assistente/pyproject.toml:180` (`[tool.ruff]`), `:184` (select/ignore), `:237` (format).
- **mypy + deptry:** só no `assistente`, via `make check` (`aplicacoes/assistente/Makefile:7-16`), local e fora do CI.
- **SonarQube:** escaneia as 3 apps (cada uma tem `sonar-project.properties`).
- **Aplicar local:** `make check` ou `task pre-commit` (`aplicacoes/assistente/pyproject.toml:172`) no `assistente`; `pre-commit` nas demais. `make install` (`Makefile:1-5`) cria a `.venv` e instala os hooks.
- **O que bloqueia merge:** `running_tests.md`.

## Nomenclatura (comum ao monorepo)

Naming **não** é enforçado por linter (o select do Ruff não inclui `N`/pep8-naming), então é convenção, não regra automática.

**Formato (casing):**

- **Módulos e pacotes:** `snake_case`.
- **Classes:** `PascalCase` (`Settings`, `EmbeddingProvider`, `HTTPException400`).
- **Funções e métodos:** `snake_case`, inclusive `async def`.
- **Constantes de módulo:** `UPPER_SNAKE` (`PROMPT_RAG`, `MAX_REQUESTS`).
- **Privado (não exportado):** prefixo `_` em funções, globais e constantes (`_start_session_runtime`, `_MAX_GAPS_PER_ROUND`). `__all__` define a API pública do módulo.

**Como nomear (substância):**

- **Idioma:** identificadores em **inglês** (funções, variáveis, classes, pacotes). **Comentários e docstrings em português.** Termo de domínio SEI sem tradução natural pode ficar em português (ex.: pacote `pergunta`); na dúvida, inglês.
- **Função: verbo primeiro** — diz a ação (`get_`, `build_`, `create_`, `calculate_`, `send_`).
- **Predicado booleano:** `is_`, `has_`, `should_`; `check_` para função de verificação (`is_document_paginated`, `has_id_process`, `should_auto_index`).
- **Descritivo, sem abreviação obscura** (`calculate_max_chunks`, não `calc_mx_chk`).
- **Constante carrega o propósito** (`PROMPT_RAG`, `_COVERAGE_FIELDS_THRESHOLD`).

## Docstrings

- **Estilo Google** (`Args:` / `Returns:` / `Raises:`) — comum ao monorepo (dominante nas 3 apps; NumPy não é usado).
- **Enforcement é por app:** o `etl-airflow` tem `[tool.ruff.lint.pydocstyle] convention = "google"` (`aplicacoes/etl-airflow/pyproject.toml:146`), mas o `select` não inclui "D" (`pyproject.toml:123`), logo a diretiva é **no-op** — docstring não é enforçada por lint em nenhuma das 3 apps. Todas seguem por convenção.
- Docstring em **módulo, classe e função/método público**; helper privado trivial pode dispensar.

## Variáveis de ambiente (por app)

Config de ambiente é **por app** — não há um `Settings` compartilhado.

- **`assistente` (pydantic-settings):** toda env var é campo do `Settings` em `aplicacoes/assistente/sei_ia/configs/settings_config.py`. Campo `UPPER_SNAKE` com `Field(default=..., alias="ASSISTENTE_<NOME>")` (`:32`) — o alias é o nome real da variável. Carregamento: `SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")` (`:20`); derivados em `model_post_init` (`:376`); singleton `settings = Settings()` (`:394`). Consumo: `from sei_ia.configs.settings_config import settings` e ler `settings.<CAMPO>`. Não usar `os.getenv` solto. Variável nova entra no `.env.example` (versionado); o dev copia para `.env` (gitignored).
- **`similaridade` e `etl-airflow`:** **não** usam pydantic-settings. `similaridade` tem config própria em `configs/`; `etl-airflow` usa config nativa do Airflow. Ver o README/`pyproject.toml` da app antes de adicionar variável.
- **Deploy** (`default.env`/`security.env`) é outro mecanismo, comum à stack — ver `building_the_project.md`.

## Convenções específicas do `assistente`

Valem só na app canônica.

- **Dupla-supressão SonarQube.** `# noqa` em regra mapeada ao Sonar exige **também** `# NOSONAR`. O hook `noqa-needs-nosonar` existe nos dois níveis: raiz do monorepo (`.pre-commit-config.yaml:54`) e no `assistente` (`aplicacoes/assistente/.pre-commit-config.yaml:29`); idem para o hook `timeout-param-needs-nosonar` (raiz `:63`, assistente `:36`). Os hooks são escopados a `aplicacoes/assistente/sei_ia/`. Complexidade local espelha o Sonar (`max-complexity = 15`, `pyproject.toml:228`).
- **Dois níveis de pre-commit.** O `.pre-commit-config.yaml` da raiz usa `language: system` (sem pin de rev) e é o ponto de entrada para commits em qualquer parte do monorepo. Os arquivos `aplicacoes/<app>/.pre-commit-config.yaml` (ex.: assistente) usam `rev` pinada (ex.: `v0.14.10`) e são o hook local da app. Ambos coexistem; a raiz espelha o CI completo via hooks adicionais. O `pre-push` da raiz reproduz o render sem segredos de `build:candidates`, roda unitários/E2E do Assistente por escopo e, para `sei_extraction`, ativa o extra `extract` para cobrir o cliente OCR. Worktrees Codex o instalam no setup; nas demais, use o comando documentado em `running_tests.md`.
- **Ignores são intencionais.** O bloco `ignore` do Ruff (`pyproject.toml:203`) documenta decisões de equipe (TRY/PLR/ERA…) — não "consertar" o ignorado. Testes têm `per-file-ignores` (`:228`): `E402`, `ARG`, `F841`.
- **Idiomas de implementação.** Dado externo vira `BaseModel` na borda. Erro sobe tipado pela hierarquia (`sei_ia/services/exceptions/`) e o handler central HTTP serializa (`sei_ia/middleware/middleware_exception_handlers.py:54`; o handler SQLAlchemy é `:36`) — não montar `JSONResponse` de erro no serviço. Integração externa atrás de uma ABC (`EmbeddingProvider`, `sei_ia/services/embedder/providers/provider_interface.py:8`). `async` nos caminhos de IO.
- **Sem fallback silencioso** — regra universal do repo, vale para todo o código.

## Divergências por app

| Aspecto | `assistente` | `similaridade` | `etl-airflow` |
|---|---|---|---|
| Ruff ruleset | E/W/F/I/B/UP/SIM/C4/RUF/ERA/ARG/FURB/C90/TRY/PLR/**S** | E/W/F/I/B/UP/SIM/C4/**RUF/TRY/S/ARG/C90** | E/W/F/I/B/UP/SIM/C4 (sem "D"; pydocstyle no-op) |
| `make check` (mypy/deptry) | sim (Makefile) | não | não |
| Docstring | Google (convenção) | Google (convenção) | Google (convenção — pydocstyle declarado mas não enforçado) |
| Env/config | pydantic `Settings`, alias `ASSISTENTE_` | `configs/` próprio | nativa do Airflow |
| Dupla-supressão Sonar (hook) | sim | — | — |

Ponteiros do ruleset: `assistente` `pyproject.toml:184`; `similaridade` `:86`; `etl-airflow` select `:123`.

## Gotchas

- **`[tool.flake8]` sem runner** (`assistente`, `pyproject.toml:221`, cognitive-complexity/CCR): não é executado por CI, Makefile nem pre-commit — config legada do espelho Sonar. O gate de complexidade é o Sonar + `mccabe` do Ruff.
- **Pin do Ruff em vários lugares** (CI + pre-commit). Subir a versão exige sincronizar todos.
