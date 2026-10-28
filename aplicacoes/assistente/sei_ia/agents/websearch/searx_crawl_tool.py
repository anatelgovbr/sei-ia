"""Agente de busca web usando SearXNG e fastCRW."""

import asyncio
import fnmatch
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from langchain_core.tools import BaseTool
from pydantic import ConfigDict, Field, PrivateAttr

from sei_ia.services.counter import token_counter

logger = logging.getLogger(__name__)

_SCRAPE_TIMEOUT = 40.0
_SITE_EXCLUDE_PREFIX = "-site:"
# Timeout mais generoso para Byparr (browser headless é mais lento que scraping estático)
_BYPARR_TIMEOUT = 50.0
# Espera interna (ms) que o Byparr aguarda ao renderizar a página. Precisa ser baixa
# o bastante para o tempo TOTAL do Byparr (overhead de browser ~14s + esta espera)
# caber dentro de _BYPARR_TIMEOUT — caso contrário o httpx aborta antes de o Byparr
# responder. O conteúdo renderizado (inclusive atributos data-*) já está no DOM em
# poucos segundos; esperar o "networkidle" de páginas pesadas só estoura o limite.
_BYPARR_MAX_TIMEOUT_MS = 10000
# Formatos que o Crawl4AI não processa
_BINARY_EXTENSIONS = {".xls", ".xlsx", ".doc", ".docx", ".ppt", ".pptx", ".zip", ".rar"}
# Conteúdo abaixo deste limite indica página sem conteúdo real
_MIN_CONTENT_LEN = 1000
# Quantas URLs extras tentar além de max_pages para compensar páginas sem conteúdo
_CRAWL_BUFFER_FACTOR = 3
# Verificar suficiência a cada N páginas boas coletadas
_EARLY_STOP_CHECK_EVERY = 2
# Limite de termos de conteúdo por query enviada ao SearXNG
# (operadores site: e a data injetada não contam)
_MAX_QUERY_TERMS = 4
# Teto de necessidades de busca (round 1). Cada necessidade vira um grupo de
# queries; limitar o número de necessidades é o primeiro fator do volume total.
_MAX_INFORMATION_NEEDS = 4
# Teto de queries geradas por necessidade. Sem este teto o LLM gera "uma query
# por item" e o volume explode, disparando rate-limit (429) no SearXNG/engines.
_MAX_QUERIES_PER_NEED = 3
# Fração do timeout a partir da qual o domínio é marcado como bloqueante
_DOMAIN_TIMEOUT_RATIO = 0.9
# Máximo de elementos com atributos data-* numéricos capturados por página
_MAX_DATA_ATTR_RECORDS = 40
# Valor data-* "métrico": contém um número com 2+ algarismos (com ou sem separador),
# evitando flags triviais de UI (ex: data-tab="1")
_DATA_ATTR_NUMERIC_RE = re.compile(r"\d[\d.,]*\d")
# Palavras-chave exclusivas de páginas de proteção anti-bot
_ANTIBOT_KEYWORDS = frozenset(
    [
        "verify you are human",
        "checking your browser",
        "please complete the security check",
        "enable javascript and cookies to continue",
        "just a moment...",
        "ddos protection by cloudflare",
        "attention required! | cloudflare",
        "verificando seu navegador",
        "verificando se você é humano",
    ]
)


def _is_antibot_page(markdown: str) -> bool:
    """Retorna True se o markdown parece uma página de proteção anti-bot."""
    text = markdown.lower()
    return any(kw in text for kw in _ANTIBOT_KEYWORDS)


# TLDs legítimos comuns — domínios com outros TLDs + caminho curto são tratados como spam.
_TRUSTED_TLDS = frozenset(
    {
        "com",
        "net",
        "org",
        "gov",
        "edu",
        "io",
        "co",
        "info",
        "com.br",
        "org.br",
        "net.br",
        "gov.br",
        "edu.br",
        "co.uk",
        "org.uk",
        "gov.uk",
        "com.au",
        "com.mx",
        "com.ar",
        "com.pt",
        "fr",
        "de",
        "it",
        "nl",
        "be",
        "ch",
        "at",
        "se",
        "no",
        "dk",
        "fi",
        "pt",
        "es",
        "pl",
        "ru",
        "cn",
        "jp",
        "kr",
        "in",
        "br",
    }
)


def _is_spam_url(url: str) -> bool:
    """Detecta URLs de domínios gerados algoritmicamente (DGA spam).

    Padrão: domínio de 2 partes (nome.tld) com TLD incomum + caminho curto.
    Ex: http://ni.om/hira, http://vavzel.ge/banud, http://bamzo.cf/pitro.
    Essas URLs disparam ContentPolicyViolation nos modelos Azure e não contêm
    conteúdo útil — filtrar antes do crawl elimina chamadas desperdiçadas ao LLM.
    """
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower().removeprefix("www.")
        parts = netloc.split(".")
        if len(parts) != 2:
            return False
        tld = parts[-1]
        # Verifica TLDs compostos como com.br
        two_part_tld = f"{parts[-2]}.{parts[-1]}" if len(parts) >= 2 else ""
        if tld in _TRUSTED_TLDS or two_part_tld in _TRUSTED_TLDS:
            return False
        path_len = len(parsed.path.strip("/"))
        return 0 < path_len <= 10
    except Exception:
        return False


def _find_next_bracket(text: str, pos: int) -> tuple[int, str, str]:
    for i in range(pos, len(text)):
        if text[i] in "{[":
            close = "}" if text[i] == "{" else "]"
            return i, text[i], close
    return -1, "", ""


def _match_balanced(text: str, start: int, open_ch: str, close_ch: str) -> int:
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i
    return -1


def _find_json_blobs(text: str) -> list[str]:  # noqa: C901, PLR0912, PLR0915  # NOSONAR
    """Encontra blocos JSON válidos embutidos em JavaScript inline.

    Usa parser de parênteses balanceados para extrair objetos ({...}) e arrays
    ([...]) JSON completos, cobrindo qualquer nível de aninhamento. Padrões
    comuns tratados:
      - dataLayer.push({...})
      - window.__data = {...}
      - var config = [...]

    Quando um bloco válido é encontrado, salta diretamente para o próximo char
    após o bloco (pos = end + 1), evitando reprocessar sub-objetos já capturados.
    Quando inválido, avança 1 posição e tenta a próxima abertura { ou [.

    Retorna no máximo 8 blobs, cada um truncado em 2 000 chars.
    """
    # Limite generoso: JSONs de dados estruturados em páginas chegam a ~15 KB.
    # Truncar muito cedo (< 6 KB) perde campos que estão no meio da estrutura.
    _MAX_BLOBS = 4
    _MAX_BLOB_CHARS = 15_000

    results: list[str] = []
    seen: set[str] = set()
    pos = 0

    while pos < len(text) and len(results) < _MAX_BLOBS:
        start, open_ch, close_ch = _find_next_bracket(text, pos)
        if start == -1:
            break
        end = _match_balanced(text, start, open_ch, close_ch)
        if end == -1:
            break
        candidate = text[start : end + 1]
        if len(candidate) >= 30:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, (dict, list)) and parsed:
                    fp = candidate[:60]
                    if fp not in seen:
                        seen.add(fp)
                        results.append(
                            json.dumps(
                                parsed, ensure_ascii=False, separators=(",", ":")
                            )[:_MAX_BLOB_CHARS]
                        )
                    pos = end + 1
                    continue
            except Exception:
                pass
        pos = start + 1

    return results


def _extract_scripts_data(html: str) -> str:
    """Extrai dados estruturados (JSON-LD + scripts inline) de HTML renderizado.

    Retorna a seção '[DADOS ESTRUTURADOS]' pronta para ser anexada a um texto,
    ou string vazia se nenhum dado for encontrado.

    Cobre duas fontes genéricas:
    - JSON-LD (<script type="application/ld+json">): padrão Schema.org de SEO.
    - Dados inline em scripts JS (sem src, < 20 KB): padrões como
      dataLayer.push({...}), window.__data = {...}, var config = [...].

    Essa função é agnóstica de domínio: qualquer site que exponha dados via
    scripts inline terá seus dados capturados automaticamente.
    """
    soup = BeautifulSoup(html, "lxml")
    return _extract_scripts_data_from_soup(soup)


def _parse_jsonld_script(script) -> str | None:
    raw = (script.string or "").strip()
    if not raw:
        return None
    try:
        return json.dumps(json.loads(raw), ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return raw[:500]


def _extract_scripts_data_from_soup(soup: "BeautifulSoup") -> str:  # type: ignore[name-defined]
    """Variante que recebe uma soup já parseada (evita double-parse em _html_to_text)."""
    parts: list[str] = []

    for script in soup.find_all("script", type="application/ld+json"):
        result = _parse_jsonld_script(script)
        if result:
            parts.append(result)

    for script in soup.find_all("script"):
        if script.get("type") == "application/ld+json" or script.get("src"):
            continue
        raw = (script.string or "").strip()
        if not raw or len(raw) > 20_000:
            continue
        parts.extend(_find_json_blobs(raw))

    section = ""
    if parts:
        section = "\n\n[DADOS ESTRUTURADOS]\n" + "\n".join(parts)
    return section + _extract_data_attributes_from_soup(soup)


def _extract_data_attributes_from_soup(soup: "BeautifulSoup") -> str:  # type: ignore[name-defined]
    """Extrai atributos data-* numéricos de elementos HTML.

    Páginas frequentemente expõem valores estruturados (métricas, indicadores) em
    atributos data-* de elementos, fora de <script> — invisíveis no markdown. Coleta
    elementos que tenham ao menos um data-* com valor numérico e preserva os demais
    data-* do mesmo elemento (que costumam identificar a que o valor se refere).
    Agnóstico de domínio: qualquer página que exponha dados em atributos é coberta.
    """
    records: list[str] = []
    seen: set[str] = set()
    for el in soup.find_all(True):
        data_attrs = {
            k: v
            for k, v in el.attrs.items()
            if k.startswith("data-") and isinstance(v, str) and v.strip()
        }
        # só aproveita o elemento se algum valor data-* parecer numérico/métrico
        if not any(_DATA_ATTR_NUMERIC_RE.search(v) for v in data_attrs.values()):
            continue
        pairs = [f"{k[5:]}={v.strip()}" for k, v in data_attrs.items() if len(v) <= 80]
        rec = " | ".join(pairs)
        if rec and rec not in seen:
            seen.add(rec)
            records.append(rec)
        if len(records) >= _MAX_DATA_ATTR_RECORDS:
            break
    if records:
        return "\n\n[ATRIBUTOS DE DADOS]\n" + "\n".join(records)
    return ""


class SearxCrawlAgent(BaseTool):
    """Agente de busca web que usa SearXNG como motor e fastCRW para extrair conteúdo."""

    name: str = "searx_crawl_search"
    description: str = (
        "Busca informações na web usando SearXNG e extrai o conteúdo completo "
        "das páginas via fastCRW. Use para informações atuais ou recentes."
    )

    searx_base_url: str = Field(description="URL base da instância SearXNG")
    fastcrw_base_url: str = Field(description="URL base da instância fastCRW")
    byparr_base_url: str | None = Field(
        default=None,
        description=(
            "URL base do Byparr (browser headless para páginas JS-renderizadas). "
            "Quando configurado, é acionado como fallback sempre que o fastCRW "
            "retornar None para uma URL. Se None, o fallback Byparr fica desativado."
        ),
    )
    llm: Any = Field(description="Instância do modelo LLM para planejamento de queries")
    compress_llm: Any = Field(
        default=None,
        description="Modelo leve (nano) para compressão de conteúdo web. Se None, desativa compressão.",
    )
    extract_llm: Any = Field(
        default=None,
        description="Modelo (mini) para extração estruturada de campos da página "
        "cheia. Mais preciso que o nano para casar rótulo↔valor em markdown "
        "ruidoso. Se None, a extração usa o compress_llm/llm.",
    )
    max_pages: int = Field(default=5, description="Número máximo de páginas por rodada")
    max_rounds: int = Field(default=2, description="Número máximo de rodadas de busca")
    llm_ctx_len: int = Field(
        default=500_000,
        description="Limite de contexto do LLM principal em tokens. "
        "Usado para decidir se o user_request precisa ser condensado antes do planejamento.",
    )
    compress_llm_ctx_len: int = Field(
        default=500_000,
        description="Limite de contexto do compress_llm em tokens. "
        "Usado para decidir se o conteúdo de uma página precisa ser comprimido.",
    )
    forced_allowed_urls: list[str] = Field(
        default_factory=list,
        description="Domínios permitidos forçados externamente (ex: modo site_restricted). "
        "Quando não vazio, sobrepõe o allowed_urls extraído do plano de busca.",
    )
    search_language: str = Field(
        default="pt-BR",
        description="Idioma/região (locale) passado ao SearXNG para localizar os "
        "resultados — evita que páginas de outros idiomas/mercados poluam a busca. "
        "Derivado do pedido pelo classificador; 'all' desativa o filtro.",
    )
    search_concurrency: int = Field(
        default=5,
        description="Máximo de buscas SearXNG simultâneas. As rodadas disparam dezenas "
        "de queries em asyncio.gather; sem limite, a rajada estoura o rate-limit (429) "
        "dos engines — sobretudo o Bing, que é o que responde de forma confiável — "
        "suspendendo-os no meio da coleta. O semáforo serializa em lotes pequenos.",
    )

    # Semáforo criado sob demanda no loop em execução (a instância é por requisição).
    _search_sem: asyncio.Semaphore | None = PrivateAttr(default=None)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _run(self, user_request: str) -> list[dict]:
        raise NotImplementedError("Use _arun para execução assíncrona")

    def _parse_llm_json(self, response) -> dict:
        """Extrai e parseia JSON da resposta do LLM, removendo blocos de código markdown."""
        content = response.content if hasattr(response, "content") else str(response)
        content = content.strip()
        if content.startswith("```"):
            parts = content.split("```")
            content = parts[1].removeprefix("json")
        return json.loads(content)

    def _deduplicate_urls(self, indices: list, to_show: list[str]) -> list[str]:
        """Converte lista de índices 1-based do LLM em URLs deduplicadas."""
        seen: set[str] = set()
        selected: list[str] = []
        for idx in indices:
            if isinstance(idx, int) and 1 <= idx <= len(to_show):
                url = to_show[idx - 1]
                if url not in seen:
                    seen.add(url)
                    selected.append(url)
        return selected

    async def _process_need(
        self,
        need: str,
        search_context: str,
        allowed_urls: list[str],
        blocked_url_patterns: list[str],
        urls_per_need: int,
    ) -> dict:
        """Gera queries, busca URLs e seleciona as melhores para uma necessidade específica."""
        queries_for_need = await self._generate_queries_for_need(need, search_context)
        need_results: list[dict] = []
        need_query_map: dict[str, str] = {}
        for q in queries_for_need:
            for cq in self._build_constrained_queries(
                q, allowed_urls, blocked_url_patterns
            ):
                for r in await self._search_searx(cq):
                    url = r.get("url", "")
                    if url and url not in need_query_map:
                        need_query_map[url] = q
                        need_results.append(r)
        all_urls = [r.get("url", "") for r in need_results if r.get("url")]
        filtered, rejected = self._filter_urls(
            all_urls, allowed_urls, blocked_url_patterns
        )
        binary = [u for u in filtered if self._is_binary_url(u)]
        filtered = [u for u in filtered if not self._is_binary_url(u)]
        selected = await self._select_urls_for_need(
            need, need_results, filtered, urls_per_need
        )
        return {
            "selected": selected,
            "query_map": {u: need_query_map.get(u, "") for u in selected},
            "title_map": {r.get("url", ""): r.get("title", "") for r in need_results},
            "snippet_map": {
                r.get("url", ""): r.get("snippet", "") for r in need_results
            },
            "rejected": rejected + binary,
        }

    def _collect_pool_from_needs(
        self,
        need_data: list[dict],
        visited_urls: set[str],
        all_rejected_urls: list[str],
    ) -> tuple[
        list[str], dict[str, str], dict[str, str], dict[str, str], dict[str, int]
    ]:
        """Combina URLs selecionadas de todas as necessidades, deduplicando (first-wins)."""
        query_map: dict[str, str] = {}
        title_map: dict[str, str] = {}
        snippet_map: dict[str, str] = {}
        pool_urls: list[str] = []
        need_map: dict[str, int] = {}
        seen_pool: set[str] = set()
        for need_idx, nd in enumerate(need_data):
            all_rejected_urls.extend(nd["rejected"])
            title_map.update(nd["title_map"])
            snippet_map.update(nd["snippet_map"])
            for url in nd["selected"]:
                if url not in seen_pool and url not in visited_urls:
                    seen_pool.add(url)
                    pool_urls.append(url)
                    query_map[url] = nd["query_map"].get(url, "")
                    need_map[url] = need_idx
        return pool_urls, query_map, title_map, snippet_map, need_map

    async def _collect_round_results(
        self,
        extra_queries: list[str],
        allowed: list[str],
        blocked: list[str],
        visited_urls: set[str],
    ) -> tuple[dict[str, str], list[dict]]:
        query_map: dict[str, str] = {}
        round_results: list[dict] = []
        for q in extra_queries:
            for cq in self._build_constrained_queries(q, allowed, blocked):
                for r in await self._search_searx(cq):
                    url = r.get("url", "")
                    if url and url not in query_map and url not in visited_urls:
                        query_map[url] = q
                        round_results.append(r)
        return query_map, round_results

    async def _plan_next_round(
        self,
        search_context: str,
        all_pages: list[dict],
        information_needs: list[str],
        all_insufficient_urls: list[str],
        visited_urls: set[str],
        round_num: int,
        allowed_urls: list[str] | None = None,
        blocked_url_patterns: list[str] | None = None,
    ) -> dict | None:
        """Avalia suficiência e planeja a próxima rodada de busca. Retorna None se encerrar."""
        _allowed = allowed_urls or []
        _blocked = blocked_url_patterns or []
        evaluation = await self._evaluate_sufficiency(
            search_context,
            all_pages,
            information_needs,
            insufficient_urls=all_insufficient_urls or None,
        )
        if evaluation.get("sufficient", True):
            logger.info(f"[Round {round_num}] Conteúdo suficiente, encerrando busca.")
            return None
        extra_queries = evaluation.get("additional_queries", [])
        if not extra_queries:
            logger.info(
                f"[Round {round_num}] Sem queries adicionais, encerrando busca."
            )
            return None
        logger.info(f"[Round {round_num}] Queries adicionais: {extra_queries}")

        query_map, round_results = await self._collect_round_results(
            extra_queries, _allowed, _blocked, visited_urls
        )

        round_urls = [r.get("url", "") for r in round_results if r.get("url")]
        filtered, rejected = self._filter_urls(round_urls, _allowed, _blocked)
        binary = [u for u in filtered if self._is_binary_url(u)]
        filtered = [u for u in filtered if not self._is_binary_url(u)]
        target = self.max_pages * _CRAWL_BUFFER_FACTOR
        pool_urls = filtered[:target]
        title_map = {r.get("url", ""): r.get("title", "") for r in round_results}
        snippet_map = {r.get("url", ""): r.get("snippet", "") for r in round_results}
        logger.info(
            f"[Round {round_num}] URLs: {len(filtered)} aceitas, "
            f"pool de crawl: {len(pool_urls)} (meta: {self.max_pages} com conteúdo real)"
        )
        return {
            "pool_urls": pool_urls,
            "query_map": query_map,
            "title_map": title_map,
            "snippet_map": snippet_map,
            "rejected": rejected + binary,
        }

    async def _arun(self, user_request: str) -> list[dict]:  # noqa: PLR0915  # NOSONAR
        logger.info(f"SearxCrawlAgent iniciado para: {user_request[:100]}...")

        all_pages: list[dict] = []
        all_rejected_urls: list[str] = []
        visited_urls: set[str] = set()
        information_needs: list[str] = []
        all_insufficient_urls: list[str] = []
        search_context: str = ""
        allowed_urls: list[str] = []
        blocked_url_patterns: list[str] = []

        for round_num in range(1, self.max_rounds + 1):
            logger.info(
                f"[Round {round_num}/{self.max_rounds}] Iniciando rodada de busca"
            )

            if round_num == 1:
                search_plan = await self._build_search_plan(user_request)
                search_context = search_plan.get("search_context") or user_request
                information_needs = search_plan.get("information_needs", []) or [
                    user_request
                ]
                # forced_allowed_urls (modo site_restricted) sobrepõe o que o LLM extraiu
                allowed_urls = self.forced_allowed_urls or search_plan.get(
                    "allowed_urls", []
                )
                blocked_url_patterns = search_plan.get("blocked_urls", [])
                logger.info(f"[Round 1] Plano de busca: {search_context[:200]}")
                logger.info(
                    f"[Round 1] Necessidades identificadas: {information_needs}"
                )

                urls_per_need = max(
                    3,
                    (self.max_pages * _CRAWL_BUFFER_FACTOR) // len(information_needs),
                )
                need_data = await asyncio.gather(
                    *[
                        self._process_need(
                            need,
                            search_context,
                            allowed_urls,
                            blocked_url_patterns,
                            urls_per_need,
                        )
                        for need in information_needs
                    ]
                )
                pool_urls, query_map, title_map, snippet_map, need_map = (
                    self._collect_pool_from_needs(
                        need_data, visited_urls, all_rejected_urls
                    )
                )
                # Mapeia cada URL para o texto da necessidade que a gerou
                url_to_need_text = {
                    url: information_needs[need_map[url]]
                    for url in pool_urls
                    if url in need_map and need_map[url] < len(information_needs)
                }
                logger.info(
                    f"[Round 1] Pool de crawl: {len(pool_urls)} URLs "
                    f"de {len(information_needs)} necessidades "
                    f"(~{urls_per_need} por necessidade)"
                )
            else:
                result = await self._plan_next_round(
                    search_context,
                    all_pages,
                    information_needs,
                    all_insufficient_urls,
                    visited_urls,
                    round_num,
                    allowed_urls=allowed_urls,
                    blocked_url_patterns=blocked_url_patterns,
                )
                if result is None:
                    break
                pool_urls = result["pool_urls"]
                query_map = result["query_map"]
                title_map = result["title_map"]
                snippet_map = result["snippet_map"]
                need_map = {}
                # Nas rodadas adicionais usa a query como contexto de compressão
                url_to_need_text = query_map
                all_rejected_urls.extend(result["rejected"])

            if not pool_urls:
                logger.info(
                    f"[Round {round_num}] Nenhuma URL para crawlear, encerrando."
                )
                break

            round_accumulated = list(all_pages)
            round_needs = list(information_needs)
            _sc = search_context

            async def _early_stop(  # noqa: B023
                current: list[dict],
                _acc: list[dict] = round_accumulated,
                _needs: list[str] = round_needs,
                _ctx: str = _sc,
            ) -> bool:
                ev = await self._evaluate_sufficiency(_ctx, _acc + current, _needs)
                return ev.get("sufficient", False)

            crawled = await self._crawl_pages(
                pool_urls,
                title_map,
                min_content_len=_MIN_CONTENT_LEN,
                need_map=need_map,
                url_to_need_text=url_to_need_text,
                early_stop_checker=_early_stop,
            )

            for page in crawled:
                url = page.get("url", "")
                page["query"] = query_map.get(url, "")
                page["snippet"] = snippet_map.get(url, "")
                visited_urls.add(url)
                all_pages.append(page)

            crawled_url_set = {page["url"] for page in crawled}
            all_insufficient_urls.extend(
                u for u in pool_urls if u not in crawled_url_set
            )
            logger.info(
                f"[Round {round_num}] Páginas com conteúdo real: {len(crawled)} "
                f"(de {len(pool_urls)} tentadas). Total acumulado: {len(all_pages)}"
            )

        if allowed_urls and not all_pages:
            domain = allowed_urls[0].lstrip("*.")
            logger.warning(
                f"[SearxCrawlAgent] Nenhum conteúdo obtido do domínio restrito: {domain}"
            )
            return [
                {
                    "content": (
                        f"Não foi possível acessar o site {domain} para obter as "
                        "informações solicitadas. O site pode estar indisponível, "
                        "bloqueando acesso automatizado ou não possuir as informações "
                        "em formato indexável."
                    ),
                    "query": search_context,
                    "references": [],
                }
            ]

        results = self._format_results(all_pages)
        results.append(
            {
                "content": "",
                "query": "",
                "references": [],
                "node": "web_search_metadata",
                "urls_consultadas": [p.get("url", "") for p in all_pages],
                "urls_bloqueadas": all_rejected_urls,
                "conteudos_utilizados": [
                    {"url": p.get("url", ""), "title": p.get("title", "")}
                    for p in all_pages
                ],
            }
        )
        return results

    async def _condense_request(self, user_request: str) -> str:
        """Condensa o user_request quando ultrapassa o limite de contexto do LLM.

        Extrai intenção, entidades e métricas relevantes para planejar a busca,
        descartando o corpo de documentos que não contribui para o planejamento.
        """
        prompt = (
            "O texto abaixo é um pedido que contém documentos extensos.\n"
            "Extraia e preserve:\n"
            "- A pergunta ou tarefa sendo solicitada\n"
            "- Nomes, siglas, identificadores e entidades específicas mencionadas\n"
            "- Métricas, campos ou dados específicos que precisam ser buscados\n"
            "- Contexto essencial que define o escopo da busca\n\n"
            "Descarte o corpo dos documentos que não seja necessário para planejar a busca.\n"
            "Saída: texto condensado preservando toda a intenção e entidades.\n\n"
            f"{user_request}"
        )
        try:
            response = await self.compress_llm.ainvoke(prompt)
            condensed = (
                response.content if hasattr(response, "content") else str(response)
            )
            return condensed.strip() or user_request
        except Exception as e:
            logger.warning(f"Erro ao condensar pedido: {e}.")
            return user_request

    async def _build_search_plan(self, user_request: str) -> dict:
        """Lê o pedido completo e produz plano de busca estruturado.

        Substitui _identify_needs. Além das necessidades de busca, gera um
        search_context — resumo compacto mas completo do que deve ser buscado —
        que substitui o user_request bruto em todas as chamadas LLM downstream,
        evitando truncagem de prompts longos e complexos.
        """
        if token_counter(user_request) >= int(self.llm_ctx_len * 0.8):
            logger.info(
                f"user_request com ~{token_counter(user_request)} tokens excede 80% "  # NOSONAR
                f"do contexto ({self.llm_ctx_len}) — condensando antes do planejamento."
            )
            user_request = await self._condense_request(user_request)

        prompt = (
            "Você é um planejador de buscas web.\n\n"
            "Leia o pedido completo abaixo e produza um plano de busca estruturado.\n\n"
            "Retorne APENAS um JSON com os campos:\n"
            "- search_context: texto compacto (máx. 500 chars) descrevendo EXATAMENTE o que "
            "precisa ser buscado: quais itens/entidades concretos, quais campos/métricas são "
            "necessários para cada um, e quais campos são gerais (não por item). "
            "Liste os itens e campos explicitamente — este texto será a única referência "
            "usada em todo o processo de busca; não omita nenhum campo obrigatório.\n"
            "- information_needs: lista de strings com cada necessidade de busca distinta. "
            f"Máximo {_MAX_INFORMATION_NEEDS} itens de alto nível. Quando o pedido requer "
            "dados individuais de múltiplos itens, crie uma necessidade por campo "
            "(ex: 'preço atual de cada item') em vez de uma necessidade por item — "
            "as queries individuais serão geradas depois.\n"
            '- allowed_urls: lista de padrões de domínio (ex: "*.gov.br") — preencher SOMENTE '
            "se o usuário EXPLICITAMENTE pedir para buscar apenas em certos sites. "
            "Caso contrário, deixar VAZIO.\n"
            "- blocked_urls: lista de padrões de domínio a bloquear — preencher SOMENTE "
            "se o usuário pedir explicitamente. Caso contrário, deixar VAZIO.\n\n"
            f"Pedido:\n{user_request}\n\n"
            "Responda APENAS com o JSON, sem texto adicional."
        )
        try:
            response = await self.llm.ainvoke(prompt)
            result = self._parse_llm_json(response)
            if not result.get("search_context"):
                raise ValueError("search_context ausente na resposta")
            # Teto determinístico: o LLM nem sempre respeita o limite pedido no prompt.
            needs = result.get("information_needs")
            if isinstance(needs, list) and len(needs) > _MAX_INFORMATION_NEEDS:
                logger.info(
                    f"[Plano] {len(needs)} necessidades reduzidas para "
                    f"{_MAX_INFORMATION_NEEDS} (teto de volume)"
                )
                result["information_needs"] = needs[:_MAX_INFORMATION_NEEDS]
            return result
        except Exception as e:
            logger.warning(f"Erro ao construir plano de busca: {e}. Usando fallback.")
            return {
                "search_context": user_request,
                "information_needs": [user_request],
                "allowed_urls": [],
                "blocked_urls": [],
            }

    async def _generate_queries_for_need(
        self, need: str, search_context: str
    ) -> list[str]:
        """Step 2: gera queries de busca dedicadas para uma informação específica."""
        prompt = (
            "Você é um especialista em buscas na web.\n\n"
            f"Contexto do pedido:\n{search_context}\n\n"
            f"Informação específica a buscar: {need}\n\n"
            "Gere queries de busca diretas e objetivas para encontrar essa informação.\n"
            "Regras:\n"
            f"- Gere no máximo {_MAX_QUERIES_PER_NEED} queries no total\n"
            f"- Máximo {_MAX_QUERY_TERMS} palavras por query\n"
            "- Você PODE usar 'site:dominio' para fontes confiáveis conhecidas, mas "
            "pelo menos uma query deve ser ampla (sem site:)\n"
            "- Se a necessidade mencionar itens específicos com identificadores reais "
            "(nomes, códigos, siglas), use esses identificadores nas queries — "
            "nunca use placeholders genéricos como 'ITEM', 'CODIGO' ou 'NOME' literalmente\n"
            "- Quando a necessidade requer dados individuais de múltiplos itens/entidades "
            "listados no contexto, gere UMA query separada por item — buscas individuais "
            "retornam resultados muito mais precisos do que agrupar vários itens em uma query\n"
            "- NÃO use inurl:, intitle: ou aspas\n\n"
            'Retorne APENAS um JSON: {"queries": ["query1", "query2", ...]}\n\n'
            "Responda APENAS com o JSON, sem texto adicional."
        )
        try:
            response = await self.llm.ainvoke(prompt)
            result = self._parse_llm_json(response)
            # Corte determinístico: o LLM pode ignorar o teto pedido no prompt.
            queries = result.get("queries", [])[:_MAX_QUERIES_PER_NEED]
            return queries or [need]
        except Exception as e:
            logger.warning(
                f"Erro ao gerar queries para '{need[:50]}': {e}. Usando fallback."
            )
            return [need]

    async def _select_urls_for_need(
        self,
        need: str,
        results: list[dict],
        filtered_urls: list[str],
        max_urls: int,
    ) -> list[str]:
        """Selects best URLs for one specific information need. LLM called only when needed."""
        if not filtered_urls:
            return []
        if len(filtered_urls) <= max_urls:
            return filtered_urls
        # Diferença pequena: SearXNG já ordena por relevância, LLM não agrega valor
        if len(filtered_urls) <= max_urls + 2:
            return filtered_urls[:max_urls]

        to_show = filtered_urls[:40]
        result_meta = {r.get("url", ""): r for r in results}
        candidates_text = "\n".join(
            f"{i + 1}. {result_meta.get(url, {}).get('title', '') or url}\n"
            f"   URL: {url}\n"
            f"   {(result_meta.get(url, {}).get('snippet', '') or '')[:120]}"
            for i, url in enumerate(to_show)
        )

        prompt = (
            "Você é um selecionador de URLs para coleta de dados na web.\n\n"
            f"Informação específica a encontrar: {need}\n\n"
            f"URLs candidatas ({len(to_show)} de {len(filtered_urls)}):\n"
            f"{candidates_text}\n\n"
            f"Selecione as {max_urls} URLs mais relevantes para encontrar "
            "exatamente essa informação.\n\n"
            "Critérios de prioridade (do mais ao menos importante):\n"
            "1. PREFIRA páginas individuais/de detalhe de um item específico "
            "(ex: página de um fundo, produto, empresa, lei ou evento concreto) "
            "em vez de páginas de listagem ou ranking geral — uma página de detalhe "
            "contém todos os dados do item; uma página de ranking traz poucos dados "
            "de muitos itens e costuma ser truncada antes de chegar nos mais relevantes.\n"
            "2. Prefira páginas com dados concretos e mensuráveis (tabelas, métricas, "
            "valores numéricos) em vez de notícias genéricas ou textos institucionais.\n"
            "3. Inclua diversidade de domínios.\n"
            "4. Exclua redes sociais, fóruns e páginas de login.\n\n"
            'Retorne APENAS um JSON: {"selected": [<números 1-based>]}\n\n'
            "Responda APENAS com o JSON, sem texto adicional."
        )
        # Seleção de URLs é ranking simples — nano é suficiente e evita concorrência
        # com o modelo standard usado em _generate_queries_for_need e _evaluate_sufficiency.
        llm = self.compress_llm or self.llm
        try:
            response = await llm.ainvoke(prompt)
            result = self._parse_llm_json(response)
            indices = result.get("selected", [])
            selected = self._deduplicate_urls(indices, to_show)
            if selected:
                logger.info(
                    f"Seleção para '{need[:50]}': {len(selected)} de {len(filtered_urls)}"
                )
                return selected
            return filtered_urls[:max_urls]
        except Exception as e:
            logger.warning(
                f"Erro na seleção para '{need[:50]}': {e}. Usando primeiras {max_urls}."
            )
            return filtered_urls[:max_urls]

    async def _evaluate_sufficiency(
        self,
        search_context: str,
        collected_pages: list[dict],
        information_needs: list[str] | None = None,
        insufficient_urls: list[str] | None = None,
    ) -> dict:
        """Avalia se o conteúdo coletado é suficiente e, se não, gera queries adicionais."""
        pages_summary = []
        for page in collected_pages:
            url = page.get("url", "")
            title = page.get("title", "")
            preview = page.get("content", "")
            pages_summary.append(f"- [{title}]({url})\n  {preview}")

        summary_text = (
            "\n\n".join(pages_summary) if pages_summary else "Nenhuma página coletada."
        )

        needs_section = ""
        if information_needs:
            needs_text = "\n".join(f"- {n}" for n in information_needs)
            needs_section = f"Informações necessárias identificadas no planejamento:\n{needs_text}\n\n"

        insufficient_section = ""
        if insufficient_urls:
            failed_text = "\n".join(f"- {u}" for u in insufficient_urls[:25])
            insufficient_section = (
                "URLs que retornaram conteúdo insuficiente (anti-bot/paywall) — "
                "evite gerar queries que levem a essas páginas ou domínios:\n"
                f"{failed_text}\n\n"
            )

        prompt = (
            "Você é um avaliador rigoroso de qualidade de busca web.\n\n"
            + needs_section
            + insufficient_section
            + "TAREFA: verifique se o conteúdo coletado contém VALORES LITERAIS para cada "
            "campo/métrica que o pedido exige.\n\n"
            "Passo 1: liste todos os campos/métricas que o pedido exige explicitamente.\n"
            "Passo 2: para cada campo, verifique se um VALOR NUMÉRICO OU TEXTUAL CONCRETO "
            "aparece explicitamente nos trechos das páginas abaixo — não apenas que a página "
            "provavelmente teria esse dado, mas que o valor está VISÍVEL no trecho.\n"
            "Passo 3: para cada campo sem valor concreto visível, elabore queries de busca "
            "combinando o nome do campo com os identificadores específicos já encontrados. "
            "Você PODE usar 'site:' para fontes confiáveis não bloqueadas.\n\n"
            "REGRA CRÍTICA: sufficient=true APENAS se TODOS os campos obrigatórios do pedido "
            "têm valores concretos visíveis nos trechos. Um campo é considerado ausente se: "
            "(a) não aparece nos trechos, (b) aparece como N/D, N/A ou similar, ou "
            "(c) a página foi listada mas o valor não está no trecho exibido.\n\n"
            "Retorne APENAS um JSON com os campos:\n"
            "- sufficient: true somente se todos os campos obrigatórios têm valores "
            "concretos visíveis nos trechos abaixo; false caso contrário\n"
            "- missing_fields: lista dos campos ainda sem valor concreto visível "
            "(obrigatório quando sufficient=false)\n"
            "- additional_queries: lista de queries para buscar os campos ausentes. "
            "Para cada campo ausente, gere pelo menos uma query específica com o nome do "
            "campo e os identificadores já encontrados. "
            "Quando um campo ausente requer dados individuais de múltiplos itens/entidades "
            "listados no pedido, gere UMA query separada por item — não agrupe vários itens "
            "em uma única query. "
            "OBRIGATÓRIO: pelo menos uma query deve ser AMPLA, sem filtro site:, para não "
            "restringir as fontes — queries com site: podem complementar, mas nunca devem "
            "ser as únicas.\n"
            "- reason: frase curta explicando o que falta ou por que é suficiente\n\n"
            f"Pedido:\n{search_context}\n\n"
            f"Trechos das páginas coletadas ({len(collected_pages)}):\n{summary_text}\n\n"
            "Responda APENAS com o JSON, sem texto adicional."
        )
        try:
            response = await self.llm.ainvoke(prompt)
            result = self._parse_llm_json(response)
            missing = result.get("missing_fields", [])
            logger.info(
                f"Avaliação de suficiência: sufficient={result.get('sufficient')}, "
                f"missing={missing}, reason={result.get('reason', '')}"
            )
        except Exception as e:
            logger.warning(f"Erro na avaliação de suficiência: {e}. Continuando busca.")
            return {
                "sufficient": False,
                "additional_queries": [],
                "reason": "Erro na avaliação.",
            }
        else:
            return result

    def _get_search_sem(self) -> asyncio.Semaphore:
        """Retorna o semáforo de buscas, criando-o sob demanda no loop atual.

        A instância do agente é criada por requisição e o semáforo precisa estar
        ligado ao loop em execução — por isso é criado na primeira busca, não na
        construção do objeto.
        """
        if self._search_sem is None:
            self._search_sem = asyncio.Semaphore(max(1, self.search_concurrency))
        return self._search_sem

    async def _search_searx(self, query: str) -> list[dict]:
        # Ponto único de normalização: toda query (round 1, rounds 2+, deep agent)
        # passa por aqui antes do SearXNG — _MAX_QUERY_TERMS termos + data.
        query = self._sanitize_query(query)
        if not query:
            return []
        params: dict[str, str] = {"q": query, "format": "json"}
        # Localiza os resultados pelo idioma/região do pedido — sem isso o SearXNG
        # busca em escopo global e páginas de outros mercados poluem a descoberta.
        if self.search_language and self.search_language.lower() != "all":
            params["language"] = self.search_language
        # Semáforo: serializa as rajadas de asyncio.gather em lotes pequenos para
        # não estourar o rate-limit dos engines (ver search_concurrency).
        async with self._get_search_sem():
            logger.info(f"Buscando no SearXNG: {query[:80]}...")
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        f"{self.searx_base_url}/search",
                        params=params,
                    )
                    response.raise_for_status()
                    data = response.json()
                    results = data.get("results", [])
                    return [
                        {
                            "url": r.get("url", ""),
                            "title": r.get("title", ""),
                            "snippet": r.get("content", ""),
                        }
                        for r in results
                        if r.get("url")
                    ]
            except httpx.TimeoutException:
                logger.warning(f"Timeout ao buscar no SearXNG para query: {query[:80]}")
                return []
            except Exception:
                logger.exception("Erro na busca SearXNG")
                return []

    @staticmethod
    def _classify_token(tok: str) -> tuple[str, str | None]:
        """Returns ('skip'|'op'|'term', value_or_None) for a single query token."""
        low = tok.lower()
        if low.startswith(("inurl:", "intitle:")):
            return "skip", None
        if low.startswith(("site:", _SITE_EXCLUDE_PREFIX)):
            prefix = (
                _SITE_EXCLUDE_PREFIX
                if low.startswith(_SITE_EXCLUDE_PREFIX)
                else "site:"
            )
            value = tok[len(prefix) :]
            netloc = urlparse(value if "://" in value else "//" + value).netloc
            domain = netloc or value.split("/")[0]
            return ("op", f"{prefix}{domain}") if domain else ("skip", None)
        if "://" in tok or "/" in tok or tok.endswith((".ghtml", ".html", ".htm")):
            return "skip", None
        cleaned = tok.replace('"', "")
        return ("term", cleaned) if cleaned else ("skip", None)

    def _sanitize_query(self, query: str) -> str:
        """Normaliza determinísticamente toda query antes de ir ao SearXNG.

        Descarta operadores proibidos (inurl:/intitle:) e caminhos de URL crus,
        reduz operadores site:/-site: ao domínio puro, remove aspas, limita os
        termos de conteúdo a _MAX_QUERY_TERMS e injeta o ano corrente como sinal
        de recência. Substitui em código as regras de formatação que antes eram
        pedidas (sem garantia) ao LLM no prompt. Operadores site: e a data não
        contam para o limite de termos.
        """
        year = str(datetime.now().year)
        terms: list[str] = []
        ops: list[str] = []
        for tok in query.split():
            kind, value = self._classify_token(tok)
            if kind == "op" and value:
                ops.append(value)
            elif kind == "term" and value:
                terms.append(value)
        terms = terms[:_MAX_QUERY_TERMS]
        date_part = [] if year in terms else [year]
        unique_ops = list(dict.fromkeys(ops))
        return " ".join(terms + date_part + unique_ops).strip()

    def _build_constrained_queries(
        self, query: str, allowed: list[str], blocked: list[str]
    ) -> list[str]:
        """Constrói queries com operadores site: para filtragem nativa no SearXNG.

        - allowed: gera uma query por domínio com 'site:dominio'
        - blocked: appends '-site:dominio' em todas as queries
        - sem restrições: retorna a query original sem alteração
        """
        blocked_ops = (
            " ".join(f"{_SITE_EXCLUDE_PREFIX}{p.lstrip('*.')}" for p in blocked)
            if blocked
            else ""
        )

        if allowed:
            queries = []
            for pattern in allowed:
                domain = pattern.lstrip("*.")
                q = f"{query} site:{domain}"
                if blocked_ops:
                    q += f" {blocked_ops}"
                queries.append(q)
            return queries

        if blocked_ops:
            return [f"{query} {blocked_ops}"]

        return [query]

    def _is_binary_url(self, url: str) -> bool:
        """Retorna True se a URL aponta para um formato que o Firecrawl não processa."""
        path = urlparse(url).path.lower()
        return any(path.endswith(ext) for ext in _BINARY_EXTENSIONS)

    def _filter_urls(
        self, urls: list[str], allowed: list[str], blocked: list[str]
    ) -> tuple[list[str], list[str]]:
        """Retorna (urls_aceitas, urls_rejeitadas). Segurança pós-busca."""
        seen: set[str] = set()
        accepted: list[str] = []
        rejected: list[str] = []
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            try:
                domain = urlparse(url).netloc
            except Exception:
                domain = url
            if _is_spam_url(url):
                rejected.append(url)
                continue
            if allowed and not any(fnmatch.fnmatch(domain, p) for p in allowed):
                rejected.append(url)
                continue
            if blocked and any(fnmatch.fnmatch(domain, p) for p in blocked):
                rejected.append(url)
                continue
            accepted.append(url)
        return accepted, rejected

    async def _crawl_pages(  # NOSONAR  # noqa: C901, PLR0912, PLR0915
        self,
        urls: list[str],
        title_map: dict[str, str] | None = None,
        min_content_len: int = 0,
        need_map: dict[str, int] | None = None,
        url_to_need_text: dict[str, str] | None = None,
        early_stop_checker: Callable[[list[dict]], Awaitable[bool]] | None = None,
        attempted_out: set[str] | None = None,
    ) -> list[dict]:
        """Extrai conteúdo das URLs via fastCRW.

        attempted_out, se fornecido, é preenchido com as URLs que efetivamente
        entraram em crawl (sucesso ou falha) — exclui as canceladas ao atingir
        o limite de max_pages. Permite ao chamador re-tentar só as não-tentadas.
        """
        if not urls:
            return []
        if title_map is None:
            title_map = {}

        # Reordena em round-robin por necessidade para garantir cobertura diversa
        if need_map:
            from collections import defaultdict

            buckets: dict[int, list[str]] = defaultdict(list)
            unmapped: list[str] = []
            for url in urls:
                if url in need_map:
                    buckets[need_map[url]].append(url)
                else:
                    unmapped.append(url)
            ordered: list[str] = []
            bucket_lists = list(buckets.values())
            max_len = max((len(b) for b in bucket_lists), default=0)
            for i in range(max_len):
                for bucket in bucket_lists:
                    if i < len(bucket):
                        ordered.append(bucket[i])
            urls = ordered + unmapped

        global_sem = asyncio.Semaphore(8)
        domain_sems: dict[str, asyncio.Semaphore] = {}
        timed_out_domains: set[str] = set()

        def _root_domain(url: str) -> str:
            netloc = urlparse(url).netloc or url
            parts = netloc.split(".")
            # Para TLDs compostos (com.br, gov.br, org.br…) pega 3 partes finais,
            # caso contrário pega 2 — garante que subdomínios do mesmo site compartilhem chave.
            _compound_slds = {"com", "gov", "org", "net", "edu", "co", "ac"}
            if len(parts) >= 3 and parts[-2] in _compound_slds:
                return ".".join(parts[-3:])
            return ".".join(parts[-2:]) if len(parts) >= 2 else netloc

        def _domain_sem(url: str) -> asyncio.Semaphore:
            root = _root_domain(url)
            if root not in domain_sems:
                domain_sems[root] = asyncio.Semaphore(1)
            return domain_sems[root]

        async def crawl_one(url: str) -> dict | None:
            domain = _root_domain(url)
            if domain in timed_out_domains:
                return None
            async with global_sem, _domain_sem(url):
                # Re-check after queueing: a prior URL from this domain may have
                # timed out while this one was waiting for the semaphore.
                if domain in timed_out_domains:
                    return None
                if attempted_out is not None:
                    attempted_out.add(url)
                t0 = time.monotonic()
                result = await self._fetch_page(
                    url, title_map.get(url, ""), min_content_len
                )
                elapsed = time.monotonic() - t0
            if result is None and elapsed >= _SCRAPE_TIMEOUT * _DOMAIN_TIMEOUT_RATIO:
                timed_out_domains.add(domain)
                logger.info(
                    f"Circuit breaker: domínio {domain} marcado ({elapsed:.0f}s)"
                )
            if result is not None and self.compress_llm:
                need_text = (url_to_need_text or {}).get(url, "")
                result["content"] = await self._compress_page(
                    result["content"], need=need_text
                )
            return result

        # Limita tasks submetidas: no máximo 4 ficam ativas ao mesmo tempo (global_sem),
        # as demais aguardam na fila sem fazer request ao servidor.
        submit_urls = urls[: self.max_pages * _CRAWL_BUFFER_FACTOR]
        tasks = [asyncio.create_task(crawl_one(url)) for url in submit_urls]
        results: list[dict] = []
        try:
            for fut in asyncio.as_completed(tasks):
                result = await fut
                if result is not None:
                    results.append(result)
                    if len(results) >= self.max_pages:
                        break
                    if (
                        early_stop_checker
                        and len(results) % _EARLY_STOP_CHECK_EVERY == 0
                        and await early_stop_checker(results)
                    ):
                        logger.info(
                            f"Parada antecipada: suficiência com {len(results)} página(s)"
                        )
                        break
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        return results

    async def _compress_page(self, content: str, need: str = "") -> str:
        """Comprime conteúdo web usando modelo nano, orientado à pergunta específica.

        Só aciona compressão quando o conteúdo ultrapassa 80% do contexto do modelo.
        """
        if token_counter(content) < int(self.compress_llm_ctx_len * 0.8):
            return content  # cabe no contexto — sem custo de compressão

        need_context = f"Pergunta que motivou esta busca: {need}\n\n" if need else ""
        prompt = (
            f"{need_context}"
            "Extraia do conteúdo abaixo apenas as informações que respondem à pergunta acima.\n"
            "Se não houver pergunta específica, remova apenas elementos estruturais sem conteúdo "
            "(menus, rodapés, cabeçalhos, propagandas, avisos de cookies, disclaimers repetidos).\n"
            "MANTENHA: todos os fatos, números, nomes, datas, percentuais, URLs, "
            "tabelas e qualquer dado concreto relacionado à pergunta.\n"
            "Escreva em estilo telegráfico: frases curtas, sem artigos, sem floreios. "
            "Preserve estrutura de tabelas markdown se houver.\n\n"
            f"{content}"
        )
        try:
            response = await self.compress_llm.ainvoke(prompt)
            compressed = (
                response.content if hasattr(response, "content") else str(response)
            )
            return compressed.strip() or content
        except Exception as e:
            logger.warning(f"Erro na compressão de página: {type(e).__name__}")
            return content

    def _html_to_text(self, html: str) -> str:
        """Converte HTML renderizado em texto limpo para extração pelo LLM.

        Extrai três camadas de conteúdo:
        1. Texto visível — remove elementos de UI (nav, footer, scripts, estilos)
           e obtém o texto legível da página via BeautifulSoup.
        2. JSON-LD (Schema.org) — <script type="application/ld+json">
        3. Dados inline — blocos JSON em scripts JS genéricos (< 20 KB, sem src).

        Usa _extract_scripts_data_from_soup para reusar a soup já parseada e
        evitar double-parse.
        """
        soup = BeautifulSoup(html, "lxml")
        # Coleta dados estruturados ANTES de remover scripts do DOM
        structured = _extract_scripts_data_from_soup(soup)
        # Texto visível: remove ruído de UI
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        visible = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))
        return visible + structured if structured else visible

    async def _fetch_page_byparr(
        self, url: str, title: str, min_content_len: int
    ) -> dict | None:
        """Extrai conteúdo de uma URL via Byparr (browser headless).

        Usado como fallback quando o fastCRW retorna None — cobre páginas que
        dependem de JavaScript para renderizar seu conteúdo principal.
        """
        try:
            async with httpx.AsyncClient(timeout=_BYPARR_TIMEOUT) as client:
                resp = await client.post(
                    f"{self.byparr_base_url}/v1",
                    json={
                        "cmd": "request.get",
                        "url": url,
                        "maxTimeout": _BYPARR_MAX_TIMEOUT_MS,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            if data.get("status") != "ok":
                logger.warning(
                    f"Byparr retornou status={data.get('status')} para {url}"
                )
                return None
            html = (data.get("solution") or {}).get("response") or ""
            if not html:
                return None
            text = self._html_to_text(html)
            if _is_antibot_page(text):
                logger.info(f"[Byparr] Página anti-bot detectada: {url}")
                return None
            if min_content_len and len(text) < min_content_len:
                logger.info(
                    f"[Byparr] Conteúdo insuficiente ({len(text)} chars): {url}"
                )
                return None
            logger.info(f"[Byparr] {url[:70]}: {len(text)} chars extraídos")
            return {"url": url, "title": title, "content": text}
        except Exception as e:
            logger.warning(f"[Byparr] Erro ao extrair {url}: {type(e).__name__}: {e}")
            return None

    @staticmethod
    def _build_page_from_fastcrw(
        data: dict, url: str, title: str, min_content_len: int
    ) -> dict | None:
        if not data.get("success"):
            logger.warning(f"fastCRW retornou success=false para {url}")
            return None
        page_data = data.get("data") or {}
        markdown = page_data.get("markdown") or ""
        if not markdown:
            return None
        if _is_antibot_page(markdown):
            logger.info(f"Página anti-bot detectada: {url}")
            return None
        if min_content_len and len(markdown) < min_content_len:
            logger.info(f"Conteúdo insuficiente ({len(markdown)} chars): {url}")
            return None
        raw_html = page_data.get("rawHtml") or ""
        content = markdown
        if raw_html:
            structured = _extract_scripts_data(raw_html)
            if structured:
                content = content + structured
                logger.debug(f"Scripts inline extraídos do rawHtml: {url[:60]}")
        return {"url": url, "title": title, "content": content}

    async def _fetch_page(
        self, url: str, title: str, min_content_len: int
    ) -> dict | None:
        """Extrai conteúdo de uma URL.

        Tenta fastCRW primeiro (rápido, scraping estático):
        - Solicita markdown (conteúdo limpo) + rawHtml (HTML bruto renderizado).
        - O markdown é o conteúdo principal; o rawHtml é usado apenas para
          extrair dados estruturados de scripts inline que o markdown não captura
          (variáveis JS, dataLayer, etc.) — agnóstico de domínio.

        Se fastCRW retornar None e o Byparr estiver configurado, tenta via
        browser headless — cobre páginas que bloqueiam scraping estático.
        """
        try:
            async with httpx.AsyncClient(timeout=_SCRAPE_TIMEOUT) as client:
                resp = await client.post(
                    f"{self.fastcrw_base_url}/v1/scrape",
                    json={"url": url, "formats": ["markdown", "rawHtml"]},
                )
                # 429 aqui é saturação do nosso fastCRW, não evidência de que o
                # site exige navegador. Encaminhar ao Byparr multiplicaria a
                # sobrecarga local exatamente durante o pico.
                if resp.status_code == 429:
                    logger.warning(
                        "fastCRW respondeu 429 para %s; pulando fallback Byparr",
                        url[:100],
                    )
                    return None
                resp.raise_for_status()
                data = resp.json()
            result = self._build_page_from_fastcrw(data, url, title, min_content_len)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning(
                    "fastCRW respondeu 429 para %s; pulando fallback Byparr",
                    url[:100],
                )
                return None
            logger.warning(f"Erro ao extrair {url}: {type(e).__name__}: {e}")
            result = None
        except Exception as e:
            logger.warning(f"Erro ao extrair {url}: {type(e).__name__}: {e}")
            result = None

        if result is None and self.byparr_base_url:
            logger.info(f"fastCRW falhou para {url[:70]} — tentando Byparr")
            result = await self._fetch_page_byparr(url, title, min_content_len)

        return result

    def _format_results(self, pages: list[dict]) -> list[dict]:
        return [
            {
                "content": page.get("content", ""),
                "query": page.get("query", ""),
                "references": [
                    {
                        "url": page.get("url", ""),
                        "title": page.get("title", ""),
                        # Snippet do SearXNG (trecho relevante à query). É o que o tooltip
                        # de citação exibe, em vez do topo da página crua (nav/cookies).
                        "snippet": page.get("snippet", ""),
                    }
                ],
            }
            for page in pages
        ]
