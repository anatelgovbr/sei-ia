"""WebResearchAgent — busca web RASA com truncar-e-armazenar (fase 8, frentes 3+4).

Alternativa ao ``DeepResearchAgent`` para o ``session_stream`` (o clássico segue
usando o DeepResearchAgent, que fica INTOCADO — decisão do Ennio 2026-07-07).

Diferença de paradigma:

- ``DeepResearchAgent``: profundo — classifica modo, extrai plano, mantém estado
  entidade x campo e roda 1 chamada de LLM POR PÁGINA (``_extract_to_state``)
  por round. Medido em ~290 generations por pesquisa.
- ``WebResearchAgent``: raso — ZERO chamadas de LLM internas. Busca no SearXNG,
  crawleia as melhores páginas, SALVA o conteúdo completo em ``web/`` no
  filesystem da sessão (escrita determinística por código, nunca ``write_file``
  de LLM) e devolve ao agente principal uma janela truncada (head+tail) + o
  caminho salvo. O ``FilesystemBackend`` enraíza a sessão, então ``read_file``/
  ``grep``/``glob`` enxergam ``web/`` de graça. A PROFUNDIDADE é decidida pelo
  agente principal: se faltou informação, ele re-chama a tool com query refinada.

Padrão truncar-e-armazenar (referência Hermes, ver phase-8 do plano): head ~75% +
tail ~25% cortados em fronteira de linha, rodapé com o caminho salvo e a dica de
leitura para paginar o miolo; imagens base64 viram ``[IMAGE: alt]``.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import Field, PrivateAttr

from sei_ia.agents.session_agent.web_evidence_gate import assess_web_evidence
from sei_ia.agents.websearch.searx_crawl_tool import SearxCrawlAgent, _is_spam_url

logger = logging.getLogger(__name__)

# Página mais curta que isto (chars de markdown) é descartada como casca/erro.
_MIN_CONTENT_LEN = 200
# Máximo de páginas do mesmo domínio por chamada (diversidade de fontes).
_MAX_PER_DOMAIN = 2
# Quantos resultados da busca (título+snippet) listar no retorno além das páginas.
_MAX_SEARCH_RESULTS_LISTED = 10
WEB_SESSION_PATH = "web/"

_IMG_BASE64_RE = re.compile(r"!\[([^\]]*)\]\(data:[^)]+\)")


def _slugify(text: str, max_len: int = 48) -> str:
    """Slug seguro para nome de arquivo a partir de título/URL."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "pagina"


def _strip_base64_images(content: str) -> str:
    """Imagem embutida em base64 vira ``[IMAGE: alt]`` (economiza contexto/disco)."""
    return _IMG_BASE64_RE.sub(lambda m: f"[IMAGE: {m.group(1) or 'imagem'}]", content)


def _truncate_with_footer(content: str, saved_path: str, budget: int) -> str:
    """Janela head(~75%)+tail(~25%) em fronteira de linha, com ponteiro pro miolo.

    ``saved_path`` é o caminho RELATIVO à raiz da sessão (ex.: ``web/x.md``) — é o
    path que o agente principal usa em ``read_file``/``grep``.
    """
    if len(content) <= budget:
        return f"{content}\n\n[Página completa salva em {saved_path}]"
    head_budget = int(budget * 0.75)
    tail_budget = budget - head_budget
    head = content[:head_budget]
    cut = head.rfind("\n")
    if cut > head_budget // 2:
        head = head[:cut]
    tail = content[-tail_budget:]
    cut = tail.find("\n")
    if 0 <= cut < tail_budget // 2:
        tail = tail[cut + 1 :]
    omitted = len(content) - len(head) - len(tail)
    return (
        f"{head}\n\n[... ~{omitted} caracteres omitidos — página completa salva em "
        f"{saved_path}; use read_file('{saved_path}', offset=N, limit=M) ou "
        f"grep para buscar no miolo ...]\n\n{tail}"
    )


class WebResearchAgent(SearxCrawlAgent):
    """Busca web rasa: pesquisa → crawleia → salva em ``web/`` → janela+ponteiro.

    Herda do ``SearxCrawlAgent`` apenas a infraestrutura de IO (``_search_searx``,
    ``_fetch_page`` com fastCRW+Byparr, filtros de spam/antibot, semáforo). NÃO
    usa nenhum dos fluxos com LLM do pai — esta tool não faz chamada de modelo.
    """

    name: str = "web_research_search"
    description: str = (
        "Busca RASA na web: pesquisa, crawleia as melhores páginas e SALVA o "
        "conteúdo completo em web/ na sessão; retorna janelas truncadas + caminho "
        "salvo. Se faltar informação, chame de novo com uma query refinada."
    )

    # LLMs do pai são obrigatórios lá; aqui são inertes (zero chamadas de LLM).
    llm: Any = Field(default=None, description="Não usado (tool sem LLM interno)")
    compress_llm: Any = Field(default=None, description="Não usado")
    extract_llm: Any = Field(default=None, description="Não usado")

    session_root: str = Field(
        description="Raiz da sessão ({SESSIONS_ROOT}/{key}); páginas vão em web/"
    )
    window_chars: int = Field(
        default=4000,
        description="Orçamento (chars) da janela devolvida por página crawleada",
    )
    max_calls: int = Field(
        default=6,
        description=(
            "Orçamento DURO de chamadas por request. Diretiva de prompt não segura "
            "agente perfeccionista (medido: 63 chamadas/28min ignorando 'máx. 4'); "
            "após o teto a tool devolve aviso para sintetizar com o que há em web/."
        ),
    )
    crawl_concurrency: int = Field(
        default=4,
        ge=1,
        description="Máximo de páginas crawleadas simultaneamente por request",
    )
    byparr_concurrency: int = Field(
        default=2,
        ge=1,
        description="Máximo de fallbacks Byparr simultâneos por request",
    )
    evidence_gate_enabled: bool = Field(
        default=False,
        description="Usa nano para condensar o lote especulativo em matriz de evidências",
    )
    evidence_gate_model: Any = Field(default=None, description="Modelo nano do gate")
    evidence_gate_question: str = Field(
        default="", description="Pergunta original, distinta da query da tool"
    )
    evidence_gate_callbacks: Any = Field(
        default=None,
        description="Callbacks do request para contabilizar o nano no trace raiz",
    )
    evidence_gate_input_chars: int = Field(
        default=24000,
        ge=1000,
        description="Teto de caracteres das páginas enviados ao gate nano",
    )

    # ------------------------------------------------------------------
    # Persistência determinística (código, nunca LLM)
    # ------------------------------------------------------------------

    def _store_page(self, url: str, title: str, content: str) -> str:
        """Grava a página em ``{session_root}/web/`` e retorna o path RELATIVO.

        Nome estável por URL (slug + sha256[:10]) → re-crawl da mesma URL
        sobrescreve em vez de duplicar. Best-effort: falha de disco não derruba
        a busca (a janela ainda é devolvida; o ponteiro indica a indisponibilidade).
        """
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
        slug = _slugify(title or urlparse(url).path or urlparse(url).netloc)
        rel_path = f"{WEB_SESSION_PATH}{slug}-{digest}.md"
        try:
            target = Path(self.session_root) / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                f"# {title or url}\n\nFonte: {url}\n\n{content}\n", encoding="utf-8"
            )
        except OSError:
            logger.exception("Falha ao salvar página %s em %s", url[:80], rel_path)
            return ""
        self._record_source(url, title, rel_path)
        return rel_path

    def _record_source(self, url: str, title: str, path: str | None) -> None:
        if not url:
            return
        state = self._web_research_state
        if state is None:
            return
        state["searched"] = True
        sources = state.setdefault("latest_sources", [])
        source = {"url": url, "title": title, "path": path}
        for index, previous in enumerate(sources):
            if previous.get("url") == url:
                sources[index] = source
                break
        else:
            sources.append(source)

    # ------------------------------------------------------------------
    # Seleção determinística de URLs (sem LLM)
    # ------------------------------------------------------------------

    def _select_urls(self, results: list[dict]) -> list[dict]:
        """Top-N pela ordem do SearXNG, sem spam, máx. 2 por domínio."""
        selected: list[dict] = []
        per_domain: dict[str, int] = {}
        seen: set[str] = set()
        for r in results:
            url = r.get("url", "")
            if not url or url in seen or _is_spam_url(url):
                continue
            domain = urlparse(url).netloc
            if per_domain.get(domain, 0) >= _MAX_PER_DOMAIN:
                continue
            seen.add(url)
            per_domain[domain] = per_domain.get(domain, 0) + 1
            selected.append(r)
            if len(selected) >= self.max_pages:
                break
        return selected

    # ------------------------------------------------------------------
    # Fluxo principal
    # ------------------------------------------------------------------

    _calls_made: int = PrivateAttr(default=0)
    _pending_searches: Any = PrivateAttr(default=None)
    _crawl_semaphore: asyncio.Semaphore | None = PrivateAttr(default=None)
    _byparr_semaphore: asyncio.Semaphore | None = PrivateAttr(default=None)
    _domain_semaphores: dict[str, asyncio.Semaphore] = PrivateAttr(default_factory=dict)
    _web_research_state: dict[str, Any] | None = PrivateAttr(default=None)

    def bind_research_state(self, state: dict[str, Any] | None) -> None:
        """Liga o coletor mutável do request sem a cópia defensiva do Pydantic."""
        self._web_research_state = state

    def _get_crawl_semaphore(self) -> asyncio.Semaphore:
        if self._crawl_semaphore is None:
            self._crawl_semaphore = asyncio.Semaphore(self.crawl_concurrency)
        return self._crawl_semaphore

    def _get_byparr_semaphore(self) -> asyncio.Semaphore:
        if self._byparr_semaphore is None:
            self._byparr_semaphore = asyncio.Semaphore(self.byparr_concurrency)
        return self._byparr_semaphore

    async def _fetch_candidate(
        self, candidate: dict[str, Any], min_content_len: int
    ) -> dict | None:
        url = candidate["url"]
        domain = urlparse(url).netloc.lower()
        domain_semaphore = self._domain_semaphores.setdefault(
            domain, asyncio.Semaphore(1)
        )
        # Adquire o limite por domínio antes do global para uma segunda URL do
        # mesmo host não ocupar vaga enquanto espera a primeira terminar.
        async with domain_semaphore, self._get_crawl_semaphore():
            return await self._fetch_page(
                url, candidate.get("title", ""), min_content_len
            )

    async def _fetch_page_byparr(
        self, url: str, title: str, min_content_len: int
    ) -> dict | None:
        """Serializa o fallback pesado separadamente do crawl estático."""
        async with self._get_byparr_semaphore():
            return await super()._fetch_page_byparr(url, title, min_content_len)

    def start_speculative(self, queries: list[str]) -> None:
        """Dispara um lote de buscas em background antes do agente principal.

        As queries já foram decompostas pelo planejador mini. Elas compartilham os
        semáforos de crawl e domínio desta instância; portanto, três pontos não
        multiplicam a concorrência de páginas. A primeira chamada da tool colhe o
        lote completo em vez de disparar uma busca adicional.
        """
        normalized = list(dict.fromkeys(q.strip() for q in queries if q and q.strip()))
        if normalized:
            self._pending_searches = asyncio.gather(
                *(self._do_search(query) for query in normalized),
                return_exceptions=True,
            )

    async def _arun(self, user_request: str, run_manager: Any = None) -> list[dict]:
        """Entrada da tool: colhe a busca especulativa (1ª vez) ou busca raso."""
        # 1ª chamada com lote especulativo pendente: colhe o que já rodou em
        # background (não busca de novo; os pontos já foram cobertos).
        if self._pending_searches is not None:
            task = self._pending_searches
            self._pending_searches = None
            try:
                batches = await task
                harvested = [
                    item
                    for batch in batches
                    if isinstance(batch, list)
                    for item in batch
                ]
                if harvested:
                    return await self._apply_evidence_gate(harvested, run_manager)
                logger.warning(
                    "[web_research] lote especulativo sem resultados; caindo p/ busca normal"
                )
            except Exception:
                logger.exception(
                    "[web_research] lote especulativo falhou; caindo p/ busca normal"
                )
        return await self._do_search(user_request.strip())

    async def _apply_evidence_gate(
        self, harvested: list[dict], run_manager: Any
    ) -> list[dict]:
        """Troca páginas brutas por matriz nano e fixa o orçamento pós-gate.

        O fallback de falha é explícito no log e mantém o comportamento anterior. Não
        limita o orçamento quando não houve veredicto válido, para não transformar uma
        falha operacional do gate em perda silenciosa de cobertura.
        """
        if not (
            self.evidence_gate_enabled
            and self.evidence_gate_model is not None
            and self.evidence_gate_question.strip()
        ):
            return harvested
        batches = [str(item.get("content", "")) for item in harvested]
        callbacks = self.evidence_gate_callbacks or (
            run_manager.get_child() if run_manager is not None else None
        )
        try:
            verdict = await assess_web_evidence(
                self.evidence_gate_question,
                batches,
                model=self.evidence_gate_model,
                callbacks=callbacks,
                max_input_chars=self.evidence_gate_input_chars,
            )
        except Exception:
            logger.exception("[web_research] gate nano falhou; devolvendo lote bruto")
            return harvested

        # As buscas especulativas já consumiram `_calls_made`. O veredicto permite
        # exatamente uma tentativa dirigida, ou nenhuma se não houver query concreta.
        self.max_calls = min(
            self.max_calls,
            self._calls_made + (1 if verdict.next_query else 0),
        )
        references = [
            reference
            for item in harvested
            for reference in item.get("references", [])
            if isinstance(reference, dict)
        ]
        logger.info(
            "[web_research] gate nano: evidencias=%d lacunas=%d busca_extra=%s",
            len(verdict.ledger),
            len(verdict.gaps),
            bool(verdict.next_query),
        )
        return [
            {
                "content": verdict.render_for_agent(),
                "query": "__evidence_gate__",
                "references": references,
            }
        ]

    async def _do_search(self, query: str) -> list[dict]:
        """Uma rodada rasa: busca → crawl paralelo → salva → janelas+ponteiros."""
        if self._web_research_state is not None:
            self._web_research_state["searched"] = True
        # Orçamento duro por request (a instância da tool é por request). Estourou:
        # devolve instrução de síntese em vez de buscar — corta o runaway serial.
        if self._calls_made >= self.max_calls:
            logger.warning(
                "[web_research] orçamento esgotado (%d chamadas); recusando query %r",
                self._calls_made,
                query[:80],
            )
            return [
                {
                    "content": (
                        f"ORÇAMENTO DE BUSCAS ESGOTADO ({self.max_calls} chamadas "
                        "nesta resposta). NÃO chame esta ferramenta novamente. "
                        "Sintetize AGORA a resposta com o que já está salvo em web/ "
                        "(use read_file/grep). Lacunas: declare em termos de FONTES "
                        "('não localizado nas fontes consultadas') — NUNCA mencione "
                        "ao usuário orçamento, ferramenta ou processo interno de busca."
                    ),
                    "query": query,
                    "references": [],
                }
            ]
        self._calls_made += 1

        # Fetch DIRETO por URL: query contendo http(s):// baixa essas páginas sem
        # passar pelo SearXNG (e sem caps de spam/domínio — URL explícita é escolha
        # deliberada do principal). Cobre o refino "abrir a ficha X" que queries
        # `site:` não alcançam (o sanitizador as embaralha e o SearXNG devolve lixo
        # — medido no diagnóstico de 2026-07-08: 4 chamadas site: = 0 páginas).
        explicit_urls = re.findall(r"https?://[^\s\"'<>\)\]]+", query)
        if explicit_urls:
            # URLs explícitas pulam a seleção (sem cap de domínio/spam).
            candidates = [
                {"url": u, "title": "", "snippet": ""}
                for u in explicit_urls[: self.max_pages]
            ]
            results = candidates
        else:
            results = await self._search_searx(query)
            if not results:
                return [
                    {
                        "content": (
                            f'A busca por "{query[:120]}" não retornou resultados. '
                            "Não repita esta mesma busca. Sintetize com as fontes e "
                            "dados já disponíveis e explicite o que não foi localizado."
                        ),
                        "query": query,
                        "references": [],
                    }
                ]
            candidates = self._select_urls(results)
        for result in results[:_MAX_SEARCH_RESULTS_LISTED]:
            self._record_source(
                str(result.get("url") or ""),
                str(result.get("title") or ""),
                None,
            )
        logger.info(
            "[web_research] iniciando lote: paginas=%d crawl_concurrency=%d "
            "byparr_concurrency=%d",
            len(candidates),
            self.crawl_concurrency,
            self.byparr_concurrency,
        )
        pages_raw = await asyncio.gather(
            *(self._fetch_candidate(r, _MIN_CONTENT_LEN) for r in candidates),
            return_exceptions=True,
        )

        blocks: list[str] = []
        references: list[dict] = []
        crawled = 0
        for cand, page in zip(candidates, pages_raw, strict=False):
            if not isinstance(page, dict) or not page.get("content"):
                continue
            crawled += 1
            url = page.get("url", cand["url"])
            title = page.get("title") or cand.get("title", "")
            content = _strip_base64_images(page["content"])
            rel_path = self._store_page(url, title, content)
            pointer = rel_path or "(falha ao salvar em disco — use só a janela)"
            window = _truncate_with_footer(content, pointer, self.window_chars)
            blocks.append(f"=== [{crawled}] {title}\nURL: {url}\n{window}")
            references.append(
                {"url": url, "title": title, "snippet": cand.get("snippet", "")}
            )

        # Resultados de busca não crawleados também orientam o refino da query.
        listing = "\n".join(
            f"- {r.get('title', '')} — {r.get('url', '')}\n  {r.get('snippet', '')}"
            for r in results[:_MAX_SEARCH_RESULTS_LISTED]
        )

        if not blocks:
            content_out = (
                f'Busca por "{query[:120]}": {len(results)} resultados, mas nenhuma '
                "página pôde ser crawleada (bloqueio/timeout). Resultados encontrados "
                f"(título/URL/snippet):\n{listing}\n\n"
                "Não repita esta mesma busca. Sintetize com os snippets e as demais "
                "fontes disponíveis; declare claramente o que não foi localizado."
            )
        else:
            content_out = (
                f'Busca por "{query[:120]}": {crawled} páginas crawleadas e salvas '
                f"em web/ (conteúdo completo no disco da sessão).\n\n"
                f"Resultados da busca:\n{listing}\n\n" + "\n\n".join(blocks)
            )

        logger.info(
            "[web_research] query=%r resultados=%d crawleadas=%d salvas_em=web/",
            query[:80],
            len(results),
            crawled,
        )
        return [{"content": content_out, "query": query, "references": references}]
