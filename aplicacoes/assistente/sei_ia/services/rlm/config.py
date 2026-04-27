"""Configurações do RLM (Recursive Language Model).

Centraliza todos os parâmetros ajustáveis do pipeline RLM v2:
modelos LLM, limites de recursão dos agentes LangGraph e orquestração TODO.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RLMConfig(BaseModel):
    """Configuração do pipeline RLM v2 (TODO + LangGraph Tools).

    Parâmetros ajustáveis para controlar o comportamento dos agentes
    (planner, explorers, synthesizer) que compõem o pipeline v2.
    Os valores padrão foram calibrados para documentos governamentais
    do SEI com até 4M tokens.

    Atributos:
        root_model_type: Tipo do modelo Root LM (standard, mini, etc.).
        sub_model_type: Tipo do modelo Sub-LM para exploradores e análise complexa.
        nano_model_type: Tipo do modelo Nano-LLM para extração rápida (ask_sub_llm effort=low).
        root_temperature: Temperatura do Root LM (baixa para determinismo).
        sub_temperature: Temperatura do Sub-LM.
        planning_recursion_limit: Limite de recursão do agente de planejamento.
        explorer_recursion_limit: Limite de recursão dos agentes exploradores.
        synthesis_recursion_limit: Limite de recursão do agente de síntese.
        max_parallel_todos: TODOs executando em paralelo.
        todo_timeout: Timeout por TODO item em segundos.
        llm_concurrency: Semáforo para chamadas LLM concorrentes.
        dep_context_max_chars: Máximo de caracteres de contexto de dependências injetado.
    """

    # --- Modelos LLM ---
    root_model_type: str = Field(
        default="standard",
        description="Tipo do modelo Root LM (standard, mini, think).",
    )
    sub_model_type: str = Field(
        default="mini",
        description="Tipo do modelo Sub-LM para exploradores e analise complexa.",
    )
    nano_model_type: str = Field(
        default="nano",
        description="Tipo do modelo Nano-LLM para extracao rapida e classificacao simples (ask_sub_llm effort=low).",
    )
    root_temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="Temperatura do Root LM.",
    )
    sub_temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="Temperatura do Sub-LM.",
    )

    # --- Limites de recursão LangGraph ---
    planning_recursion_limit: int = Field(
        default=10,
        description="Limite de recursao do agente de planejamento.",
    )
    explorer_recursion_limit: int = Field(
        default=50,
        description="Limite de recursao dos agentes exploradores.",
    )
    synthesis_recursion_limit: int = Field(
        default=15,
        description="Limite de recursao do agente de sintese.",
    )

    # --- Orquestração TODO (v2) ---
    max_parallel_todos: int = Field(
        default=5,
        description="Max TODOs executando em paralelo.",
    )
    todo_timeout: int = Field(
        default=600,
        description="Timeout por TODO item em segundos.",
    )
    llm_concurrency: int = Field(
        default=15,
        description="Semaphore para chamadas LLM concorrentes.",
    )

    # --- Contexto de dependências ---
    dep_context_max_chars: int = Field(
        default=50_000,
        description="Maximo de caracteres de contexto de dependencias injetado nos exploradores.",
    )

    # --- Threshold direto vs RLM ---
    direct_llm_token_threshold: int = Field(
        default=30_000,
        description="Documentos com menos tokens que este valor vao direto para o LLM "
        "(com injecao de prompt do intent), sem passar pelo pipeline RLM.",
    )
