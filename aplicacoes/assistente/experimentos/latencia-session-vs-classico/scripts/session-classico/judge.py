"""LLM-as-a-judge para o experimento session vs stream tradicional.

Avalia uma resposta de endpoint contra a rubrica do item do dataset `comparativo`
(ancorada no conteudo real do processo 8116731). Roda o juiz pelo MESMO proxy
LiteLLM do app (cliente OpenAI-compativel, alias de modelo `standard`), que e o
caminho de LLM deste deployment — sem SDK de provider especifico.

Metricas emitidas (uma score Langfuse por metrica):
  - groundedness   [0..1]  cada afirmacao sustentada pelos docs (ou fontes web citadas)
  - completeness   [0..1]  cobertura dos elementos_obrigatorios (respeita credito_parcial)
  - citation_quality [0..1] cita doc-fonte / URLs conforme exigido
  - hallucination  [bool]  asseriu algum indicador de alucinacao / fato nao suportado
  - negativa_correta [bool] (so categoria 'negativa') reconheceu "nao consta" em vez de inventar
  - overall        [0..1]  correcao holistica vs gold_answer_exemplo

Nao decide aprovacao/reprovacao sozinho — emite as metricas; a agregacao
session-vs-classico fica no runner do experimento.

Uso programatico (pelo runner):
    from judge import judge_response, JudgeConfig
    result = judge_response(question, expected_output, answer_text, cfg)

Uso CLI (smoke test com uma resposta de exemplo):
    uv run python experimentos/latencia-session-vs-classico/scripts/session-classico/judge.py --selftest
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
from dataclasses import dataclass, field

from openai import OpenAI

from sei_ia.configs.settings_config import settings

# Nomes canonicos das metricas (use os mesmos no runner e na config de score do Langfuse).
METRIC_NAMES_NUMERIC = ["groundedness", "completeness", "citation_quality", "overall"]
METRIC_NAMES_BOOL = ["hallucination", "negativa_correta"]


# O proxy LiteLLM apontado pelo .env (rhgicdpdin02:8080) expoe os IDS REAIS dos
# modelos, nao os aliases (`standard`/`mini`). O time da API key so tem acesso aos
# ids reais. O alias `standard` do app corresponde a `seiia-ds` (ver litellm_config.yaml).
_ALIAS_TO_REAL = {
    "standard": "seiia-ds",
    "mini": "seiia-ds-mini",
    "nano": "seiia-ds-nano",
}


def _resolve_model() -> str:
    # Judge roda no mini (seiia-ds-mini / gpt-5.4-mini) por padrao: a avaliacao e
    # barata e o mini basta para aplicar a rubrica. Override por EXP_JUDGE_MODEL_ALIAS
    # (standard/mini/nano, ou um id real do proxy).
    alias = os.environ.get("EXP_JUDGE_MODEL_ALIAS") or settings.LITELLM_MINI_MODEL_NAME
    return _ALIAS_TO_REAL.get(alias, alias)


def _proxy_url() -> str:
    # Fonte da verdade: o .env raiz do monorepo aponta o proxy que serve os modelos
    # (rhgicdpdin02:8080). Esse valor e injetado em LITELLM_PROXY_URL no ambiente do
    # processo (o runner carrega o .env raiz). So cai no settings se o env nao tiver.
    return os.environ.get("LITELLM_PROXY_URL") or settings.LITELLM_PROXY_URL


def _proxy_key() -> str:
    return (
        os.environ.get("LITELLM_PROXY_API_KEY")
        or settings.LITELLM_PROXY_API_KEY
        or "not-needed"
    )


def _resolve_temperature() -> float | None:
    if os.environ.get("EXP_JUDGE_OMIT_TEMPERATURE") == "true":
        return None
    return 0.0


@dataclass
class JudgeConfig:
    """Config do juiz. Usa o proxy LiteLLM e a API key do .env raiz (rhgicdpdin02:8080),
    chamando o modelo pelo id real `seiia-ds` (o mesmo que o alias `standard` resolve)."""

    model: str = field(default_factory=_resolve_model)
    base_url: str = field(default_factory=_proxy_url)
    api_key: str = field(default_factory=_proxy_key)
    temperature: float | None = field(default_factory=_resolve_temperature)
    max_tokens: int = 1500


_SYSTEM = (
    "Voce e um avaliador rigoroso e imparcial de respostas de um assistente sobre "
    "processos administrativos do SEI/ANATEL. Avalie com base na rubrica fornecida "
    "(ancorada nos documentos reais do processo). Nunca premie informacao que a rubrica "
    "marca como indicador de alucinacao. "
    "IMPORTANTE: o gold e um exemplo MINIMO de referencia, nao uma lista exaustiva do "
    "que os documentos contem. Os autos tem MAIS detalhes do que o gold cita (datas de "
    "registro na Junta, numeros de protocolo, procuracoes, atos societarios, etc.). "
    "Detalhe ESPECIFICO e PLAUSIVEL que nao aparece no gold NAO e alucinacao nem reduz "
    "groundedness so por ausencia no gold. So e alucinacao o que (a) CONTRADIZ a rubrica, "
    "(b) bate num indicador de alucinacao listado, ou (c) e claramente inventado/implausivel. "
    "Na duvida sobre um detalhe fundamentavel, NAO marque alucinacao. Riqueza de detalhe "
    "correto e bom, nao penalize. REGRA DURA: se voce se pegar escrevendo no rationale "
    "algo como 'pode ser sustentavel', 'nao esta na rubrica mas e plausivel' ou 'alem do "
    "necessario', entao hallucination=false — so marque true com contradicao ou invencao "
    "CLARA. Para perguntas de categoria 'negativa', a resposta CORRETA e reconhecer que a "
    "informacao nao consta nos autos; inventar o valor pedido e erro grave. Na negativa, "
    "contexto adicional ancorado (onde procurou, o que os docs contem no lugar) NAO e "
    "alucinacao — e evidencia de diligencia; nao penalize. "
    "Para perguntas web, avalie se a fonte CITADA sustenta a informacao, sem exigir um "
    "site ou dominio especifico quando a rubrica nao o exigir. Fonte ausente reduz "
    "citation_quality e, quando impede verificar a afirmacao, groundedness. Fonte ausente "
    "NUNCA e alucinacao por si so: marque hallucination=true apenas para fato falso, "
    "fonte inventada, contradicao ou conclusao que a evidencia apresentada nao sustenta. "
    "Responda APENAS com JSON valido, sem texto fora dele."
)

_INSTRUCT = """\
Pergunta feita ao assistente:
{pergunta}

Categoria da pergunta: {categoria}

RUBRICA (verdade de referencia, ancorada nos documentos do processo):
- Resposta-modelo (gold): {gold_exemplo}
- Elementos obrigatorios: {obrigatorios}
- Condicoes de credito parcial: {parcial}
- Indicadores de alucinacao (NUNCA premiar): {alucinacao}
- Documento-fonte esperado: {doc_fonte}
- Regra: {regra}

RESPOSTA DO ASSISTENTE A SER AVALIADA:
\"\"\"
{resposta}
\"\"\"

Avalie a resposta e devolva um JSON com EXATAMENTE estas chaves:
{{
  "groundedness": <float 0..1, fracao das afirmacoes sustentadas pelos documentos ou, em perguntas web, pelas fontes citadas. NAO reduza so porque um detalhe plausivel nao esta no gold — o gold e minimo. Em web, reduza quando a falta de fonte impedir verificar uma afirmacao; isso nao torna hallucination=true por si so>,
  "completeness": <float 0..1, cobertura dos elementos obrigatorios, respeitando o credito parcial>,
  "citation_quality": <float 0..1, qualidade da citacao de documento-fonte / URLs conforme exigido pela categoria>,
  "hallucination": <true/false, true SOMENTE se a resposta (a) afirma algum indicador de alucinacao listado, (b) CONTRADIZ a rubrica, (c) inventa fato ou fonte, ou (d) tira conclusao nao sustentada pela evidencia que apresenta. Detalhe plausivel ausente do gold e falta de citacao, isoladamente, NAO contam como alucinacao>,
  "negativa_correta": <true/false/null, so para categoria 'negativa': true se reconheceu corretamente que nao consta nos autos; null se a categoria nao for 'negativa'>,
  "overall": <float 0..1, correcao holistica: cobre os elementos obrigatorios sem contradizer a rubrica. Detalhe correto a mais do que o gold NAO reduz>,
  "rationale": "<2-4 frases justificando, citando o que faltou ou o que CONTRADIZ os autos>"
}}
Use 0..1 com ate 2 casas decimais. Seja severo com alucinacao REAL (contradicao, invencao ou indicador listado) e com falta de citacao quando exigida — mas NAO penalize riqueza de detalhe fundamentavel."""


@dataclass
class JudgeResult:
    scores_numeric: dict[str, float]
    scores_bool: dict[str, bool | None]
    rationale: str
    raw: dict
    usage: dict | None


def _client(cfg: JudgeConfig) -> OpenAI:
    return OpenAI(base_url=cfg.base_url, api_key=cfg.api_key)


def build_prompt(question_text: str, expected_output: dict, answer_text: str) -> str:
    eo = expected_output or {}
    return _INSTRUCT.format(
        pergunta=question_text,
        categoria=eo.get("categoria", "?"),
        gold_exemplo=eo.get("gold_answer_exemplo") or eo.get("gold_answer", ""),
        obrigatorios=json.dumps(
            eo.get("elementos_obrigatorios", []), ensure_ascii=False
        ),
        parcial=eo.get("credito_parcial", ""),
        alucinacao=json.dumps(eo.get("indicadores_alucinacao", []), ensure_ascii=False),
        doc_fonte=eo.get("doc_fonte", ""),
        regra=eo.get("regra", ""),
        resposta=answer_text,
    )


def judge_response(
    question_text: str,
    expected_output: dict,
    answer_text: str,
    cfg: JudgeConfig | None = None,
) -> JudgeResult:
    """Roda o juiz e devolve as metricas estruturadas. Nao escreve no Langfuse."""
    cfg = cfg or JudgeConfig()
    prompt = build_prompt(question_text, expected_output, answer_text)

    # Data corrente no system: sem ela o juiz (cutoff antigo) marcava referencias
    # datadas do ano corrente como "futuras/inventadas" em casos websearch
    # (falso-positivo medido no WEB-FII-01, 2026-07-08).
    hoje = _dt.date.today().isoformat()
    system = (
        f"{_SYSTEM} DATA DE HOJE: {hoje}. Datas/referencias ate a data de hoje sao "
        "normais (a resposta pode vir de busca web recente); NUNCA trate uma "
        "referencia como 'futura' ou inventada apenas por ser posterior ao seu "
        "conhecimento de treino."
    )

    temperature = {} if cfg.temperature is None else {"temperature": cfg.temperature}
    resp = _client(cfg).chat.completions.create(
        model=cfg.model,
        max_tokens=cfg.max_tokens,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        **temperature,
    )
    content = resp.choices[0].message.content or "{}"
    data = json.loads(content)  # falha alto se o juiz nao devolver JSON valido

    def _f(k: str) -> float:
        v = float(data[k])
        return max(0.0, min(1.0, v))

    is_negativa = (expected_output or {}).get("categoria") == "negativa"
    neg = data.get("negativa_correta")
    usage = getattr(resp, "usage", None)
    normalized_usage = None
    if usage is not None:
        prompt_details = getattr(usage, "prompt_tokens_details", None)
        completion_details = getattr(usage, "completion_tokens_details", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        cache_read = int(getattr(prompt_details, "cached_tokens", 0) or 0)
        raw_cache_write = getattr(prompt_details, "cache_write_tokens", None)
        if raw_cache_write is None:
            raw_cache_write = getattr(prompt_details, "cache_creation_tokens", None)
        cache_write = None if raw_cache_write is None else int(raw_cache_write)
        output = int(getattr(usage, "completion_tokens", 0) or 0)
        reasoning = int(getattr(completion_details, "reasoning_tokens", 0) or 0)
        input_uncached = max(0, prompt_tokens - cache_read)
        normalized_usage = {
            "role": "judge",
            "deployment": cfg.model,
            "reported_model": getattr(resp, "model", None),
            "input": input_uncached,
            "cache_read": cache_read,
            "cache_write": cache_write,
            "output": output,
            "reasoning": reasoning,
            "total": prompt_tokens + output,
            "generations": 1,
        }
    return JudgeResult(
        scores_numeric={k: _f(k) for k in METRIC_NAMES_NUMERIC},
        scores_bool={
            "hallucination": bool(data["hallucination"]),
            "negativa_correta": (
                bool(neg) if is_negativa and neg is not None else None
            ),
        },
        rationale=str(data.get("rationale", "")),
        raw=data,
        usage=normalized_usage,
    )


def emit_scores(langfuse, trace_id: str, result: JudgeResult) -> None:
    """Escreve as metricas como scores Langfuse no trace dado (chamado pelo runner).

    `langfuse` e uma instancia Langfuse ja autenticada. data_type explicito:
    NUMERIC para [0..1], BOOLEAN para flags. O rationale vai no comment de overall.
    """
    for name, val in result.scores_numeric.items():
        langfuse.create_score(
            name=name,
            value=val,
            trace_id=trace_id,
            data_type="NUMERIC",
            comment=(result.rationale if name == "overall" else None),
        )
    for name, val in result.scores_bool.items():
        if val is None:
            continue  # negativa_correta so existe para a categoria negativa
        langfuse.create_score(
            name=name,
            value=1 if val else 0,
            trace_id=trace_id,
            data_type="BOOLEAN",
        )


def _selftest() -> None:
    """Smoke test SINTETICO do juiz (sem PII real do processo).

    Usa nomes/datas ficticios so para exercitar o caminho do juiz contra o proxy;
    a rubrica real (com nomes do processo) vive no Langfuse interno, nao aqui.
    """
    expected = {
        "categoria": "temporal",
        "gold_answer_exemplo": (
            "O responsavel atual e a Pessoa B, desde 01/01/2024, substituindo a Pessoa A. "
            "(Fonte: doc SEI 0000001.)"
        ),
        "elementos_obrigatorios": [
            "Pessoa B",
            "desde 01/01/2024",
            "substituiu Pessoa A",
        ],
        "credito_parcial": "Credito parcial se acertar o nome sem a data.",
        "indicadores_alucinacao": [
            "Pessoa A como responsavel atual",
            "data anterior a 2024",
        ],
        "doc_fonte": "doc SEI 0000001",
        "regra": "Ancorar nos documentos do processo.",
    }
    pergunta = "Quem e o responsavel atual e desde quando? (exemplo sintetico)"
    boa = (
        "O responsavel atual e a Pessoa B, desde 01/01/2024, quando substituiu a "
        "Pessoa A (doc SEI 0000001)."
    )
    ruim = "O responsavel atual e a Pessoa A, desde 2021."

    cfg = JudgeConfig()
    print(f"[selftest] juiz: model={cfg.model} base_url={cfg.base_url}")
    for label, ans in [("BOA", boa), ("RUIM(alucinada)", ruim)]:
        r = judge_response(pergunta, expected, ans, cfg)
        print(f"\n--- resposta {label} ---")
        print(" numeric:", r.scores_numeric)
        print(" bool:", r.scores_bool)
        print(" rationale:", r.rationale)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
    else:
        print("nada a fazer; use --selftest ou importe judge_response/emit_scores")
