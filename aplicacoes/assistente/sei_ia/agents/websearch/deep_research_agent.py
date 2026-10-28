"""Agente de pesquisa profunda com estado por entidade (padrão ReAct).

Resolve queries multi-entidade onde os dados de cada entidade estão distribuídos
em dezenas de páginas diferentes — situação em que o SearxCrawlAgent falha porque
o avaliador de suficiência exige todos os campos visíveis simultaneamente.

Fluxo:
  [1] _extract_research_plan   → tipo de entidade, campos obrigatórios, queries de descoberta
  [Fase 1] _discover_entities  → encontra nomes/ids das entidades concretas a pesquisar
  Estado inicial: {entidade: {campo: None}} para todas as entidades

  loop (até cobertura suficiente ou max_rounds):
    [2] _identify_gaps          → pares (entidade, campo) ainda vazios
    [3] _check_coverage         → suficiente se 80% das entidades têm 75% dos campos
    [4] _generate_targeted_queries  → queries cirúrgicas por entidade x campo
    [5] SearXNG → URLs
    [6] fastCRW → conteúdo (stack existente, inalterada)
    [7] _extract_to_state       → preenche estado a partir de cada página
    [log] _log_progress         → detalha o que foi coletado e o quanto falta

  [8] _aggregate_state  → compila estado em conteúdo estruturado para o LLM de resposta
"""

import asyncio
import logging
import re
from urllib.parse import urlparse

from pydantic import Field

from sei_ia.agents.websearch.searx_crawl_tool import (
    _CRAWL_BUFFER_FACTOR,
    _MAX_QUERY_TERMS,
    SearxCrawlAgent,
)
from sei_ia.services.counter import token_counter

logger = logging.getLogger(__name__)

# Limiar de cobertura por entidade: fração de entidades que precisam atingir o limiar de campos
_COVERAGE_ENTITIES_THRESHOLD = 0.80
# Limiar de campos por entidade: fração de campos que uma entidade precisa ter preenchidos
_COVERAGE_FIELDS_THRESHOLD = 0.75
# Máximo de gaps enviados ao LLM gerador de queries por rodada
_MAX_GAPS_PER_ROUND = 30
# Máximo de queries geradas por rodada
_MAX_QUERIES_PER_ROUND = 20
# Rounds consecutivos sem nenhuma extração de um campo para abandoná-lo
_MAX_FIELD_EMPTY_ROUNDS = 2
# Locale default quando o classificador não infere um idioma/região válido
_DEFAULT_LOCALE = "pt-BR"
# Multiplicador de breadth da fase de descoberta sobre o pool de crawl normal.
# Páginas de índice/ranking/comparação consolidam vários itens com vários campos
# de uma vez — medições mostram que a pré-extração delas é ~1 ordem de grandeza
# mais densa (campos preenchidos por página) do que as buscas de perfil por
# entidade dos rounds seguintes. Crawlear mais páginas de descoberta é o lever de
# maior ROI para a cobertura multi-entidade.
_DISCOVERY_CRAWL_FACTOR = 2
# Tentativas extras de descoberta quando a 1ª rodada rende menos entidades que o
# esperado: o agente refaz a busca com queries mais amplas (voltadas a listas) em
# vez de seguir com poucas entidades. Limitado para não estourar latência/custo.
_MAX_DISCOVERY_RETRIES = 3
# Teto do pool de over-discover: descobrir mais candidatos que o pedido para a poda
# por evidência ter de onde escolher, sem explodir o custo de coleta.
_MAX_DISCOVER_POOL = 20
# Filtro de forma do identificador na descoberta: quando há um grupo relevante de
# identificadores COMPACTOS (código/sigla de token único e curto), nomes longos são
# anomalias (tipo diferente vazado de fonte mista) e são descartados.
_COMPACT_ID_MAXLEN = 12
_MIN_COMPACT_CLUSTER = 3
# Sinais numéricos para promoção determinística de 'simple' → 'deep': um pedido
# com pelo menos _DEEP_MIN_ITEMS itens distintos, cada um exigindo
# _DEEP_MIN_FIELDS campos, é multi-entidade e deve seguir o fluxo profundo —
# mesmo que o classificador nano o rotule 'simple' de forma instável. Espelham o
# guard de plano trivial em _arun (≥3 campos e ≥3 entidades), que reverte para
# 'simple' caso o plano completo extraído não confirme a multi-entidade.
_DEEP_MIN_ITEMS = 3
_DEEP_MIN_FIELDS = 3
# Limiares de complexidade da pesquisa deep. Acima de _DEEP_MIN_*, o esforço é
# calibrado pelo porte do pedido em vez de sempre usar os parâmetros máximos.
# "medium": ≤ _COMPLEXITY_MEDIUM_MAX_ITEMS entidades E ≤ _COMPLEXITY_MEDIUM_MAX_FIELDS
#           campos → deep com rounds/retries/over-discover reduzidos.
# "complex": qualquer coisa maior → deep completo.
_COMPLEXITY_MEDIUM_MAX_ITEMS = 5
_COMPLEXITY_MEDIUM_MAX_FIELDS = 7
_COMPLEXITY_MEDIUM_MAX_ROUNDS = 3
_COMPLEXITY_MEDIUM_DISCOVER_EXTRA = 2
_COMPLEXITY_MEDIUM_RETRIES = 1
_COMPLEXITY_COMPLEX_DISCOVER_EXTRA = 5
# Teto de links internos candidatos enviados ao LLM de seleção no modo
# site_restricted com URL: limita o tamanho do prompt sem perder cobertura
# (páginas-índice costumam ter centenas de links; só precisamos de uma amostra).
_MAX_LINK_CANDIDATES = 150


class DeepResearchAgent(SearxCrawlAgent):
    """Agente de pesquisa profunda com estado por entidade x campo.

    Herda toda a infraestrutura do SearxCrawlAgent (SearXNG, fastCRW, filtros,
    compressão de página, condensação de request) e substitui apenas o loop
    de coleta por um fluxo ReAct orientado a cobertura.

    Para queries simples (poucas entidades, poucos campos), delega automaticamente
    para o SearxCrawlAgent pai.
    """

    name: str = "deep_research_search"
    description: str = (
        "Agente de pesquisa profunda para queries multi-entidade. "
        "Mantém estado por entidade/campo e para quando cobertura for suficiente."
    )
    coverage_entities_threshold: float = Field(
        default=_COVERAGE_ENTITIES_THRESHOLD,
        description="Fração mínima de entidades com campos suficientes para encerrar.",
    )
    coverage_fields_threshold: float = Field(
        default=_COVERAGE_FIELDS_THRESHOLD,
        description="Fração mínima de campos preenchidos para uma entidade ser 'coberta'.",
    )

    # ------------------------------------------------------------------
    # Métodos puramente computacionais (sem chamada a LLM)
    # ------------------------------------------------------------------

    def _identify_gaps(
        self,
        state: dict[str, dict[str, str | None]],
        required_fields: list[str],
    ) -> list[tuple[str, str]]:
        """Retorna lista de (entidade, campo) ainda sem valor no estado."""
        return [
            (entity, field)
            for entity, fields in state.items()
            for field in required_fields
            if fields.get(field) is None
        ]

    def _check_coverage(
        self,
        state: dict[str, dict[str, str | None]],
        required_fields: list[str],
    ) -> bool:
        """Retorna True quando cobertura suficiente para encerrar a pesquisa.

        sufficient = fração de entidades com >= coverage_fields_threshold campos
                     preenchidos >= coverage_entities_threshold
        """
        if not state or not required_fields:
            return False
        total_fields = len(required_fields)
        covered = sum(
            1
            for fields in state.values()
            if sum(1 for f in required_fields if fields.get(f) is not None)
            / total_fields
            >= self.coverage_fields_threshold
        )
        return covered / len(state) >= self.coverage_entities_threshold

    def _match_entity(self, entity: str, entities_list: list[str]) -> str | None:
        """Encontra correspondência entre um nome extraído e as entidades do estado.

        Primeiro tenta match exato (case-insensitive), depois parcial.
        """
        norm = entity.upper().strip()
        for e in entities_list:
            if e.upper() == norm:
                return e
        for e in entities_list:
            if norm in e.upper() or e.upper() in norm:
                return e
        return None

    def _match_field(self, field: str, fields_list: list[str]) -> str | None:
        """Encontra correspondência entre um campo extraído e os campos obrigatórios.

        Normaliza espaços e hífens para underscore antes de comparar.
        """
        norm = field.lower().replace(" ", "_").replace("-", "_")
        for f in fields_list:
            if f.lower() == norm:
                return f
        for f in fields_list:
            f_norm = f.lower().replace(" ", "_").replace("-", "_")
            if norm in f_norm or f_norm in norm:
                return f
        return None

    @staticmethod
    def _format_fonte(fonte: str, url_to_idx: dict[str, int]) -> str:
        """Formata a anotação de fonte de um campo no conteúdo agregado.

        Com url_to_idx e a URL mapeada, emite (fonte: <web_N>) — marcador que o LLM
        reproduz para virar citação clicável. Sem mapa, mantém (fonte: url) textual.
        """
        if not fonte:
            return ""
        idx = url_to_idx.get(fonte)
        if idx is not None:
            return f" (fonte: <web_{idx}>)"
        return f" (fonte: {fonte})"

    def _render_entity_block(
        self,
        entity: str,
        fields: dict,
        required_fields: list[str],
        url_to_idx: dict[str, int],
    ) -> list[str]:
        lines = [f"### {entity}"]
        missing: list[str] = []
        for field in required_fields:
            entry = fields.get(field)
            if entry is None:
                missing.append(field)
                lines.append(f"- {field}: [não encontrado]")
                continue
            valor = entry.get("valor", "") if isinstance(entry, dict) else str(entry)
            fonte = entry.get("fonte", "") if isinstance(entry, dict) else ""
            lines.append(f"- {field}: {valor}{self._format_fonte(fonte, url_to_idx)}")
        if missing:
            lines.append(f"  ⚠ Campos não encontrados: {', '.join(missing)}")
        lines.append("")
        return lines

    def _aggregate_state(
        self,
        state: dict[str, dict[str, str | None]],
        searchable_fields: list[str],
        non_searchable_fields: list[str] | None = None,
        url_to_idx: dict[str, int] | None = None,
    ) -> str:
        """Compila o estado em texto estruturado por entidade para o LLM de resposta.

        O conteúdo agregado é inserido como primeiro item nos resultados, fornecendo
        ao LLM final dados organizados por entidade em vez de páginas brutas.

        searchable_fields são os campos efetivamente buscados (presentes no estado).
        non_searchable_fields são campos que o pedido exige mas que não se buscam
        (identidade, calculáveis, autorais, metadado de fonte) — o LLM de resposta
        os preenche a partir dos dados buscados, da identidade da entidade e das
        próprias referências.

        url_to_idx mapeia cada URL-fonte ao índice do marcador de citação <web_N>.
        Quando fornecido, cada dado é anotado com (fonte: <web_N>) e o LLM é instruído
        a reproduzir o marcador — assim o deep também gera citações clicáveis. Sem o
        mapa, mantém-se o formato antigo (fonte: url) em texto puro.
        """
        required_fields = searchable_fields  # campos rastreados no estado
        non_searchable_fields = non_searchable_fields or []
        url_to_idx = url_to_idx or {}
        if not state:
            return "Nenhuma entidade pesquisada."

        # Calcula cobertura geral para informar o LLM
        total_slots = len(state) * len(required_fields) if required_fields else 0
        filled_slots = sum(
            1
            for fields in state.values()
            for f in required_fields
            if fields.get(f) is not None
        )
        pct = filled_slots / total_slots * 100 if total_slots else 0

        citation_instruction = (
            "Cada dado abaixo traz sua fonte no formato (fonte: <web_N>). Ao afirmar "
            "um dado na resposta, REPRODUZA EXATAMENTE o marcador <web_N> "
            "correspondente ao final da frase ou da linha da tabela — ele será "
            "convertido na citação clicável da fonte. "
            if url_to_idx
            else ""
        )
        lines = [
            "=== DADOS COLETADOS POR ENTIDADE ===",
            "",
            "INSTRUÇÃO PARA O ASSISTENTE: use TODOS os dados abaixo para responder "
            "de forma completa e direta ao pedido do usuário. "
            "Para campos marcados como [não encontrado], informe apenas que o dado "
            "não estava disponível nas fontes consultadas — NÃO recuse responder nem "
            "diga que os dados são insuficientes para responder. "
            + citation_instruction
            + f"Cobertura geral: {filled_slots}/{total_slots} campos ({pct:.0f}%).",
            "",
        ]
        for entity, fields in state.items():
            lines.extend(
                self._render_entity_block(entity, fields, required_fields, url_to_idx)
            )

        if non_searchable_fields:
            lines.extend(
                [
                    "=== CAMPOS A PREENCHER SEM BUSCA ===",
                    "Os campos abaixo são exigidos pelo pedido mas NÃO foram buscados "
                    "porque não são fatos publicados em fontes. Preencha-os assim:",
                    "- Identidade da entidade (nome/código): use o identificador da "
                    "entidade já listado acima.",
                    "- Calculáveis: derive a partir dos campos buscados (ex.: razões, "
                    "somas) apenas quando os valores necessários existirem acima; caso "
                    "contrário marque como não disponível.",
                    "- Autorais (justificativas, recomendações, análises): redija com "
                    "base nos dados buscados acima, sem inventar fatos novos.",
                    "- Metadado de fonte (links/datas das fontes): use as referências "
                    "das páginas consultadas.",
                    f"Campos: {', '.join(non_searchable_fields)}",
                    "",
                ]
            )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Logging detalhado de progresso
    # ------------------------------------------------------------------

    def _log_progress(
        self,
        state: dict[str, dict[str, str | None]],
        required_fields: list[str],
        round_num: int,
    ) -> None:
        """Loga progresso detalhado: cobertura por entidade e gaps restantes."""
        total_entities = len(state)
        total_fields = len(required_fields)
        if total_entities == 0 or total_fields == 0:
            logger.info(
                f"[Round {round_num}] Estado vazio — aguardando descoberta de entidades."
            )
            return

        total_slots = total_entities * total_fields
        filled_slots = sum(
            1
            for fields in state.values()
            for f in required_fields
            if fields.get(f) is not None
        )
        covered = sum(
            1
            for fields in state.values()
            if sum(1 for f in required_fields if fields.get(f) is not None)
            / total_fields
            >= self.coverage_fields_threshold
        )
        pct_slots = filled_slots / total_slots * 100
        gaps_remaining = total_slots - filled_slots

        logger.info(
            f"[Round {round_num}] ══ COBERTURA ══ "
            f"{covered}/{total_entities} entidades OK | "
            f"{filled_slots}/{total_slots} campos ({pct_slots:.0f}%) | "
            f"{gaps_remaining} gaps restantes | "
            f"meta: {self.coverage_entities_threshold * 100:.0f}% entidades"
        )
        for entity, fields in state.items():
            filled_names = [f for f in required_fields if fields.get(f) is not None]
            missing_names = [f for f in required_fields if fields.get(f) is None]
            entity_pct = len(filled_names) / total_fields * 100
            status = (
                "✅"
                if len(filled_names) / total_fields >= self.coverage_fields_threshold
                else "⏳"
            )
            logger.info(
                f"  {status} {entity}: {len(filled_names)}/{total_fields} "
                f"({entity_pct:.0f}%)"
                + (f" — falta: {missing_names}" if missing_names else " — completo")
            )

    # ------------------------------------------------------------------
    # Chamadas a LLM
    # ------------------------------------------------------------------

    async def _classify_search_mode(self, user_request: str) -> dict:
        """Classifica o pedido em um modo de busca (chamada curta no modelo nano).

        Retorna {"mode": ..., "allowed_domain": ..., "target_url": ...}. Modos atuais:
        - "single_url": processar (traduzir/resumir/consultar) apenas UMA página dada.
        - "site_restricted": o usuário restringe a busca a um único site/domínio.
        - "deep": dados de cada item espalhados em muitas fontes (pesquisa por item).
        - "simple": default — perguntas factuais, listagens, consulta de conteúdo.

        O default é 'simple'; os demais modos só são acionados quando claramente
        pedidos. Outros modos virão em iterações futuras.
        """
        llm = self.compress_llm or self.llm
        # compress_llm é construído com a tag default "agents:explorador" (ver
        # get_model(agent_tag="explorador") nos chamadores); esta chamada
        # específica é classificação de modo de busca, não exploração de
        # conteúdo — rebind pra tag correta sem recriar o client HTTP.
        llm = llm.bind(extra_body={"tags": ["agents:triagem_busca"]})
        prompt = (
            "Classifique o pedido de busca web abaixo. Responda APENAS com JSON: "
            '{"mode": "...", "allowed_domain": "...", "target_url": "...", '
            '"language": "...", "item_count": 0, "fields_per_item": 0}.\n\n'
            '- "single_url": o usuário quer apenas processar (traduzir, resumir, '
            "consultar) o conteúdo de UMA página específica já informada por URL, SEM "
            "consultar outras fontes. Em target_url coloque a URL informada.\n"
            '- "url_search": o usuário informa uma URL como base/referência E pede '
            "explicitamente para TAMBÉM consultar/usar OUTRAS fontes além dela "
            "(ex: 'resuma esta página e consulte outras fontes'). Em target_url "
            "coloque a URL informada.\n"
            '- "site_restricted": o usuário pede para buscar/consultar APENAS em um '
            "site específico (nomeado ou informado por URL) e NÃO pede para consultar "
            "outras fontes. Em allowed_domain coloque só o domínio (host), sem esquema "
            "nem caminho. Se o site foi informado por uma URL explícita (com esquema/"
            "caminho), coloque essa URL também em target_url, para baixá-la diretamente "
            "em vez de procurá-la no buscador.\n"
            '- "deep": o pedido exige reunir, para CADA item de um conjunto de itens, '
            "vários dados que normalmente estão distribuídos em páginas/fontes "
            "diferentes, exigindo pesquisa individual por item. Só escolha deep quando "
            "NÃO existe uma única página de índice/lista/tabela que já consolide os "
            "itens com os dados pedidos.\n"
            '- "simple": qualquer outro caso — perguntas factuais, listagens que uma '
            "página de índice já responde, ou consulta que precisa de outras fontes além "
            "de uma página dada. Deixe allowed_domain e target_url vazios.\n\n"
            "Em language coloque o locale (formato 'idioma-REGIÃO', ex: 'pt-BR', "
            "'en-US', 'es-ES') que melhor localiza as fontes para este pedido — "
            "infira pelo idioma do texto e pela região/mercado a que o pedido se "
            "refere. Se não houver região clara, use o locale do idioma do pedido.\n\n"
            "Em item_count coloque quantos itens DISTINTOS a resposta precisa cobrir "
            "(ex: 10 para 'Top 10' ou 'liste 10 ...'; 1 para uma pergunta sobre um "
            "único assunto/entidade). Em fields_per_item coloque quantos atributos/"
            "dados distintos o pedido exige POR item (ex: para cada item, nome, preço, "
            "categoria e data = 4). Conte com cuidado — esses números são usados para "
            "decidir o esforço da busca.\n\n"
            "Na dúvida, escolha simple.\n\n"
            f"Pedido:\n{user_request}\n\n"
            "Responda APENAS com o JSON."
        )
        try:
            response = await llm.ainvoke(prompt)
            result = self._parse_llm_json(response)
            mode = str(result.get("mode") or "simple").strip().lower()
            if mode not in {
                "simple",
                "deep",
                "site_restricted",
                "single_url",
                "url_search",
            }:
                mode = "simple"
            domain = str(result.get("allowed_domain") or "").strip()
            # normaliza: remove esquema e caminho se o LLM tiver incluído
            if "://" in domain:
                domain = domain.split("://", 1)[1]
            domain = domain.split("/", 1)[0].strip()
            target_url = str(result.get("target_url") or "").strip()
            if mode == "site_restricted" and not domain:
                mode = "simple"  # sem domínio não há o que restringir
            if mode == "single_url" and not target_url:
                mode = "simple"  # sem URL não há página única a processar
            if mode == "url_search" and not target_url:
                mode = "simple"  # sem URL-base, vira busca simples
            # Promoção determinística simple → deep: o classificador nano é instável
            # ao rotular pedidos multi-entidade (vários itens, vários campos cada).
            # Os sinais numéricos são mais estáveis que o juízo categórico; quando
            # ambos cruzam o limiar, força deep. Não toca single_url/url_search/
            # site_restricted (pedidos explícitos de URL/site). Se o plano completo
            # extraído em _arun não confirmar a multi-entidade, o guard de plano
            # trivial reverte para simple — sem custo de chamada LLM adicional.
            item_count = self._safe_int(result.get("item_count"))
            fields_per_item = self._safe_int(result.get("fields_per_item"))
            if (
                mode == "simple"
                and item_count >= _DEEP_MIN_ITEMS
                and fields_per_item >= _DEEP_MIN_FIELDS
            ):
                logger.info(
                    f"[Classificador] Promovendo 'simple' → 'deep': "
                    f"item_count={item_count} (≥{_DEEP_MIN_ITEMS}), "
                    f"fields_per_item={fields_per_item} (≥{_DEEP_MIN_FIELDS}) "
                    "indicam pedido multi-entidade."
                )
                mode = "deep"
            return {
                "mode": mode,
                "allowed_domain": domain,
                "target_url": target_url,
                "language": self._normalize_locale(result.get("language")),
            }
        except Exception as e:
            logger.warning(f"Erro ao classificar modo de busca: {e}. Usando 'simple'.")
            return {
                "mode": "simple",
                "allowed_domain": "",
                "target_url": "",
                "language": _DEFAULT_LOCALE,
            }

    @staticmethod
    def _safe_int(value: object) -> int:
        """Converte um sinal numérico do classificador em int, 0 se inválido.

        O modelo nano pode devolver número como string ('10'), float (10.0) ou
        algo inesperado — qualquer valor não conversível vira 0, o que apenas
        deixa de promover para deep (decisão conservadora).
        """
        try:
            return int(float(value))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _normalize_locale(value: object) -> str:
        """Normaliza o locale do classificador para 'idioma-REGIÃO' (ex: pt-BR).

        Aceita 'all' (desativa o filtro do SearXNG). Qualquer valor fora do
        formato esperado cai no default — evita passar lixo ao SearXNG.
        """
        loc = str(value or "").strip().replace("_", "-")
        if loc.lower() == "all":
            return "all"
        m = re.fullmatch(r"([a-zA-Z]{2})(?:-([a-zA-Z]{2}))?", loc)
        if not m:
            return _DEFAULT_LOCALE
        lang = m.group(1).lower()
        region = m.group(2)
        return f"{lang}-{region.upper()}" if region else lang

    async def _fetch_single_url(self, url: str, search_context: str) -> list[dict]:
        """Modo single_url: baixa o conteúdo de UMA página e retorna sem buscar.

        Usa o fetch da stack existente (fastCRW + fallback Byparr) — é uma única
        página, então o JS importa e a latência é baixa. Se não conseguir o conteúdo,
        retorna a mensagem amigável de página inacessível.
        """
        logger.info(f"[DeepResearchAgent] Modo 'single_url' — fetch direto de {url}")
        page = await self._fetch_page(url, "", 0)
        if page is None:
            logger.warning(f"[single_url] Não foi possível obter conteúdo de {url}")
            return [
                {
                    "content": (
                        f"Não foi possível acessar a página {url}. O site pode estar "
                        "indisponível, bloqueando acesso automatizado por proteção "
                        "anti-bot, ou sem conteúdo em formato indexável."
                    ),
                    "query": search_context,
                    "references": [],
                }
            ]
        page["query"] = search_context
        results = self._format_results([page])
        results.append(
            {
                "content": "",
                "query": "",
                "references": [],
                "node": "web_search_metadata",
                "urls_consultadas": [url],
                "urls_bloqueadas": [],
                "conteudos_utilizados": [{"url": url, "title": page.get("title", "")}],
            }
        )
        return results

    @staticmethod
    def _extract_internal_links(content: str, domain: str) -> list[tuple[str, str]]:
        """Extrai links do mesmo domínio do markdown de uma página.

        Retorna lista de (url, texto_âncora) deduplicada por URL, restrita ao
        host informado (e seus subdomínios). Usada no modo site_restricted com
        URL para navegar a partir de uma página-índice sem recorrer ao buscador.
        """
        links: list[tuple[str, str]] = []
        seen: set[str] = set()
        # markdown: [texto](url) ou [texto](url "título") — para no espaço/paren.
        for match in re.finditer(r"\[([^\]]*)\]\((https?://[^)\s]+)", content):
            text = match.group(1).strip()
            link_url = match.group(2).strip()
            host = (urlparse(link_url).hostname or "").lower()
            if not host or not (host == domain or host.endswith(f".{domain}")):
                continue
            # normaliza removendo fragmento para deduplicar âncoras da mesma página
            link_url = link_url.split("#", 1)[0]
            if not link_url or link_url in seen:
                continue
            seen.add(link_url)
            links.append((link_url, text))
        return links

    async def _select_relevant_links(
        self, search_context: str, candidates: list[tuple[str, str]], k: int
    ) -> list[str]:
        """Pede ao LLM até k links mais relevantes para a necessidade do usuário.

        Prompt agnóstico de domínio: recebe a necessidade e a lista de links
        (texto + URL) e devolve apenas as URLs mais promissoras. Valida o retorno
        contra os candidatos para não inventar URLs.
        """
        llm = self.compress_llm or self.llm
        pool = candidates[:_MAX_LINK_CANDIDATES]
        valid_urls = {url for url, _ in pool}
        listing = "\n".join(
            f'{i}. "{text or "(sem título)"}" -> {url}'
            for i, (url, text) in enumerate(pool, 1)
        )
        prompt = (
            "Abaixo está a NECESSIDADE do usuário e uma lista de links internos "
            "extraídos de uma página-índice de um site. Escolha os links que mais "
            "provavelmente contêm a informação pedida (ex.: páginas de "
            "agenda/lista/detalhe), ignorando navegação genérica, institucional ou "
            "irrelevante.\n\n"
            f"NECESSIDADE:\n{search_context}\n\n"
            f"LINKS:\n{listing}\n\n"
            f'Responda APENAS com JSON: {{"urls": [ate {k} URLs, em ordem de '
            "relevância]}. Use as URLs exatamente como aparecem na lista. Se nenhum "
            'link parecer relevante, responda {"urls": []}.'
        )
        try:
            response = await llm.ainvoke(prompt)
            result = self._parse_llm_json(response)
            chosen = result.get("urls") or []
            selected = [u for u in chosen if isinstance(u, str) and u in valid_urls]
            return selected[:k]
        except Exception as e:
            logger.warning(f"Erro ao selecionar links internos: {e}.")
            return []

    async def _fetch_site_navigated(
        self, seed_url: str, domain: str, search_context: str
    ) -> list[dict]:
        """Modo site_restricted com URL: baixa a página-semente e navega links internos.

        Em vez de gastar buscas site: no SearXNG (que dependem de engines
        frequentemente bloqueados), baixa a URL informada, extrai seus links do
        mesmo domínio, deixa o LLM escolher os mais relevantes e baixa um número
        limitado deles. Agrega tudo (semente + páginas seguidas) com citações.
        """
        # Se o classificador não isolou o host, deriva da própria URL-semente.
        domain = (domain or urlparse(seed_url).hostname or "").lower()
        logger.info(
            f"[DeepResearchAgent] Modo 'site_restricted' com URL — fetch-first de "
            f"{seed_url} + navegação interna (domínio {domain})."
        )
        seed = await self._fetch_page(seed_url, "", 0)
        if seed is None:
            logger.warning(
                f"[site_restricted/url] Página-semente inacessível: {seed_url}"
            )
            return [
                {
                    "content": (
                        f"Não foi possível acessar a página {seed_url}. O site pode "
                        "estar indisponível, bloqueando acesso automatizado por "
                        "proteção anti-bot, ou sem conteúdo em formato indexável."
                    ),
                    "query": search_context,
                    "references": [],
                }
            ]

        seed["query"] = search_context
        pages = [seed]

        k = max(self.max_pages - 1, 0)
        candidates = self._extract_internal_links(seed.get("content", ""), domain)
        candidates = [c for c in candidates if c[0] != seed_url]
        if k and candidates:
            selected = await self._select_relevant_links(search_context, candidates, k)
            logger.info(
                f"[site_restricted/url] {len(candidates)} links internos; "
                f"seguindo {len(selected)}: {selected}"
            )
            followed = await asyncio.gather(
                *(self._fetch_page(u, "", 0) for u in selected)
            )
            for u, page in zip(selected, followed, strict=True):
                if page is not None:
                    page["query"] = search_context
                    pages.append(page)
                else:
                    logger.info(f"[site_restricted/url] link inacessível: {u}")

        results = self._format_results(pages)
        results.append(
            {
                "content": "",
                "query": "",
                "references": [],
                "node": "web_search_metadata",
                "urls_consultadas": [p.get("url", "") for p in pages],
                "urls_bloqueadas": [],
                "conteudos_utilizados": [
                    {"url": p.get("url", ""), "title": p.get("title", "")}
                    for p in pages
                ],
            }
        )
        return results

    async def _extract_research_plan(self, user_request: str) -> dict:
        """Extrai plano de pesquisa estruturado: tipo de entidade, campos e queries.

        Retorna um dict com:
        - entity_type: categoria do item que se repete no pedido
        - required_fields: campos obrigatórios por entidade
        - known_entities: entidades já identificadas no pedido (vazio = descobrir)
        - discovery_queries: queries para descobrir quais entidades pesquisar
        - expected_entity_count: quantidade esperada de entidades
        - search_context: resumo compacto do objetivo da pesquisa
        """
        prompt = (
            "Você é um planejador de pesquisa profunda na web.\n\n"
            "Analise o pedido abaixo e retorne um JSON com os campos:\n"
            "- entity_type: a categoria do item que se repete no pedido "
            "(o substantivo que nomeia cada item do conjunto a pesquisar).\n"
            "- required_fields: lista dos campos obrigatórios a coletar POR entidade. "
            "Use identificadores curtos sem espaços — sem acentos e com underscore "
            "para separar palavras (ex: nome, tipo, valor_atual, categoria, data_inicio). "
            "Inclua TODOS os campos explicitamente pedidos no prompt.\n"
            "- searchable_fields: subconjunto de required_fields cujos valores são FATOS "
            "concretos publicados em fontes (números, datas, categorias que aparecem "
            "literalmente nas páginas) e que portanto fazem sentido BUSCAR. "
            "NÃO inclua aqui (serão preenchidos sem busca):\n"
            "  * campos de identidade da própria entidade — o nome/código que a "
            "identifica, já conhecido quando a entidade é determinada;\n"
            "  * campos calculáveis a partir de outros campos (razões, somas, "
            "diferenças, classificações derivadas);\n"
            "  * campos autorais ou de opinião (justificativas, recomendações, análises "
            "que quem responde redige, não que existem prontos numa fonte);\n"
            "  * campos de metadado sobre as próprias fontes (links/URLs das fontes, "
            "datas de acesso).\n"
            "Quando em dúvida sobre um campo, inclua-o em searchable_fields.\n"
            "- known_entities: lista de entidades JÁ IDENTIFICADAS no pedido "
            "(códigos ou nomes próprios citados explicitamente). "
            "Deixe VAZIO [] se as entidades precisam ser descobertas — quando o "
            "pedido nomeia apenas a categoria e uma quantidade, não os itens.\n"
            "- discovery_queries: lista de 4-6 queries para descobrir quais entidades "
            "pesquisar. Obrigatório quando known_entities estiver vazio. "
            "REGRAS para as queries de descoberta (uma busca BEM FEITA traz só páginas "
            "do tipo de entidade pedido — se traria resultados de outro assunto, está "
            "malformada):\n"
            "  * Cada query = o termo que identifica o TIPO de entidade (use o nome "
            "COMPLETO e não-ambíguo, não apenas a sigla) + no MÁXIMO 1 característica "
            "que DEFINE o subconjunto (o que a entidade É / a que classe pertence). "
            "NÃO use condições de QUALIFICAÇÃO/CORTE do pedido como termo de busca "
            "(limiares, mínimos/máximos, 'baixa/alta X', métricas de desempenho, nomes "
            "de campos): isso é filtro aplicado DEPOIS da coleta; como termo de busca "
            "estreita demais e traz páginas de matéria em vez de listas da entidade.\n"
            "  * PROIBIDO montar a query a partir de superlativos/classificadores "
            "genéricos ('melhores', 'ranking', 'maiores', 'top', 'piores') junto só com "
            "o tipo: combinados com a data, casam com 'melhores/ranking de <ano>' de "
            "assuntos não relacionados e poluem a busca. Descreva a entidade pelo que "
            "ela É, não por 'ser a melhor'.\n"
            "  * Pelo menos 2 queries com 'site:' apontando para fontes especializadas "
            "no tipo de entidade.\n"
            "  * Pelo menos 2 queries devem usar termos de LISTAGEM AMPLA ('lista', "
            "'lista completa', 'todos os', 'comparativo', 'tabela') para encontrar "
            "páginas-diretório que enumeram muitas entidades de uma vez — não apenas "
            "perfis individuais.\n"
            f"  * Queries curtas (máx {_MAX_QUERY_TERMS} termos).\n"
            "- expected_entity_count: número esperado de entidades "
            "(ex: 10 para 'Top 10').\n"
            "- search_context: texto compacto (máx 400 chars) descrevendo o objetivo, "
            "critérios de filtragem e campos obrigatórios.\n\n"
            f"Pedido:\n{user_request}\n\n"
            "Responda APENAS com o JSON, sem texto adicional."
        )
        try:
            response = await self.llm.ainvoke(prompt)
            result = self._parse_llm_json(response)
            if not result.get("required_fields"):
                raise ValueError("required_fields ausente na resposta do LLM")
            result["searchable_fields"] = self._resolve_searchable_fields(result)
            return result
        except Exception as e:
            logger.warning(f"Erro ao extrair plano de pesquisa profunda: {e}")
            return {
                "entity_type": "entidade",
                "required_fields": [],
                "searchable_fields": [],
                "known_entities": [],
                "discovery_queries": [user_request[:80]],
                "expected_entity_count": 5,
                "search_context": user_request[:400],
            }

    async def _generate_broader_discovery_queries(
        self,
        entity_type: str,
        search_context: str,
        found_entities: list[str],
        needed: int,
    ) -> list[str]:
        """Gera queries de descoberta MAIS AMPLAS quando a 1ª rodada rendeu poucas.

        Voltadas a páginas que ENUMERAM muitas entidades do tipo (catálogos, listas,
        comparativos) — e não páginas sobre uma só. Domínio-agnóstico: usa só o
        entity_type e o objetivo, sem conhecer o domínio concreto.
        """
        found_txt = ", ".join(found_entities[:30]) or "(nenhuma)"
        prompt = (
            f"Uma primeira busca para descobrir entidades rendeu POUCAS (faltam ~{needed} "
            "para o esperado). Gere de 5 a 8 "
            "NOVAS queries para encontrar PÁGINAS QUE ENUMERAM/LISTAM MUITAS entidades "
            f"do tipo '{entity_type}' de uma vez (catálogos, listas completas, tabelas "
            "comparativas), em vez de páginas que falam de uma só.\n"
            "REGRAS:\n"
            "  * Use o nome COMPLETO do tipo + um termo que indique LISTAGEM AMPLA "
            "(ex.: 'lista', 'lista completa', 'todos os', 'comparativo', 'tabela').\n"
            "  * PROIBIDO superlativos de mérito ('melhores', 'ranking', 'maiores', "
            "'top') e PROIBIDO critérios de filtro/limiares — poluem ou estreitam.\n"
            "  * Pelo menos 1 query com 'site:' para uma fonte que costume manter "
            "catálogo/lista do tipo.\n"
            f"  * Queries curtas (máx {_MAX_QUERY_TERMS} termos).\n"
            f"Objetivo da pesquisa: {search_context}\n"
            f"Entidades já encontradas (não precisa repetir o foco nelas): {found_txt}\n"
            'Responda APENAS um JSON: {"queries": ["...", "..."]}'
        )
        try:
            response = await self.llm.ainvoke(prompt)
            result = self._parse_llm_json(response)
            queries = result.get("queries", [])
            cleaned = [str(q).strip() for q in queries if str(q).strip()]
            return cleaned[:8]
        except Exception as e:
            logger.warning(f"Erro ao gerar queries de descoberta amplas: {e}")
            return []

    @staticmethod
    def _resolve_searchable_fields(plan: dict) -> list[str]:
        """Determina os campos que o loop ReAct deve efetivamente buscar.

        Intersecta searchable_fields (subconjunto factual indicado pelo LLM) com
        required_fields, preservando a ordem de required_fields. Se o LLM não
        indicar nenhum campo pesquisável válido, retorna required_fields inteiro —
        fallback conservador que reproduz o comportamento anterior (busca tudo).
        """
        required: list[str] = plan.get("required_fields") or []
        raw = plan.get("searchable_fields")
        if not isinstance(raw, list):
            return list(required)
        marked = {str(f).strip() for f in raw if str(f).strip()}
        searchable = [f for f in required if f in marked]
        return searchable or list(required)

    async def _extract_entity_names(
        self,
        content: str,
        entity_type: str,
        expected_count: int,
        required_fields: list[str],
    ) -> list[str]:
        """Extrai nomes/identificadores de entidades de um conteúdo de página."""
        if not content.strip():
            return []

        fields_hint = ", ".join(required_fields[:5]) if required_fields else ""
        # Extração de NOME de entidade exige discriminar o tipo exato (não confundir
        # com tipos vizinhos/categoria mais ampla nem com entidades só citadas) — usa
        # o modelo mais forte (mini), como na extração de campos.
        llm = self.extract_llm or self.compress_llm or self.llm
        prompt = (
            f"Você está analisando uma página para encontrar {entity_type}(s).\n\n"
            f"Extraia os identificadores únicos (nomes, códigos, siglas) "
            f"de {entity_type}(s) que aparecem no conteúdo abaixo.\n"
            "Extraia APENAS instâncias individuais e concretas. NÃO extraia:\n"
            f"  * o termo genérico que nomeia a própria categoria (ex: a sigla/plural "
            f"de '{entity_type}') — não é uma instância;\n"
            "  * índices, benchmarks, cestas ou agregados que reúnem várias instâncias "
            "(são referência de comparação, não itens individuais);\n"
            "  * nomes de categorias, segmentos, setores ou classificações;\n"
            f"  * itens de um TIPO DIFERENTE do pedido — se a página misturar tipos "
            f"(uma categoria mais ampla que contém '{entity_type}', ou tipos vizinhos "
            f"parecidos), extraia SÓ os que são exatamente '{entity_type}' e descarte "
            "o resto;\n"
            f"  * entidades apenas CITADAS ou RELACIONADAS (aparecem associadas a uma "
            f"instância — ex.: partes, donos, parceiros, componentes — mas não são elas "
            f"próprias um '{entity_type}').\n"
            "IMPORTANTE: preserve a ordem em que aparecem na página — "
            "se for um ranking ou lista ordenada por relevância, o 1º lugar vem primeiro.\n"
            "Se a página contiver uma lista alfabética completa (todos os itens começando "
            "com letras diferentes, sem contexto de ranking ou destaque), extraia apenas "
            f"os {expected_count} primeiros que apareçam em contexto de análise ou destaque, "
            "não os primeiros da ordem alfabética.\n"
            + (
                f"Campos que precisaremos buscar depois: {fields_hint}\n"
                if fields_hint
                else ""
            )
            + f"Retorne no máximo {expected_count} identificadores.\n\n"
            'Retorne APENAS um JSON: {"entities": ["id1", "id2", ...]}\n\n'
            f"{content}"
        )
        try:
            response = await llm.ainvoke(prompt)
            result = self._parse_llm_json(response)
            entities = result.get("entities", [])
            cleaned = [str(e).strip() for e in entities if e]
            return [e for e in cleaned if not self._is_type_word(e, entity_type)]
        except Exception as e:
            logger.warning(f"Erro ao extrair nomes de entidades: {e}")
            return []

    @staticmethod
    def _is_type_word(identifier: str, entity_type: str) -> bool:
        """True se o identificador é apenas o termo genérico da categoria.

        Rede de segurança determinística para o caso de o LLM devolver o próprio
        termo do tipo (no singular ou plural) em vez de uma instância concreta.
        Comparação por normalização simples (caixa + 's' final).
        """

        def _norm(s: str) -> str:
            return s.strip().lower().rstrip("s")

        et = _norm(entity_type)
        return bool(et) and _norm(identifier) == et

    @staticmethod
    def _compute_complexity(item_count: int, fields_per_item: int) -> str:
        """Classifica o esforço necessário em 'simple', 'medium' ou 'complex'.

        Derivado deterministicamente dos sinais numéricos do classificador —
        não exige chamada LLM adicional. Calibra max_rounds, over-discover e
        retries de descoberta proporcionalmente ao porte real do pedido:

        - simple:  abaixo dos limiares mínimos deep → delega ao SearxCrawlAgent.
        - medium:  multi-entidade de porte médio (≤ 5 itens e ≤ 7 campos) →
                   deep com parâmetros reduzidos (3 rounds, menos over-discover).
        - complex: grande (≥ 6 itens OU ≥ 8 campos) → deep completo.
        """
        if item_count < _DEEP_MIN_ITEMS or fields_per_item < _DEEP_MIN_FIELDS:
            return "simple"
        if (
            item_count <= _COMPLEXITY_MEDIUM_MAX_ITEMS
            and fields_per_item <= _COMPLEXITY_MEDIUM_MAX_FIELDS
        ):
            return "medium"
        return "complex"

    @staticmethod
    def _dedup_queries(queries: list[str], seen: set[str]) -> tuple[list[str], int]:
        deduped: list[str] = []
        skipped = 0
        for q in queries:
            q_norm = q.strip().lower()
            if q_norm not in seen:
                seen.add(q_norm)
                deduped.append(q.strip())
            else:
                skipped += 1
        return deduped, skipped

    @staticmethod
    def _find_covered_entities(
        deduped: list[str], uncovered_entities: list[str]
    ) -> set[str]:
        covered: set[str] = set()
        for q in deduped:
            if "site:" not in q.lower():
                for entity in uncovered_entities:
                    if entity.lower() in q.lower():
                        covered.add(entity)
        return covered

    def _fill_open_queries(
        self,
        deduped: list[str],
        uncovered_entities: list[str],
        entity_type: str,
        seen: set[str],
    ) -> None:
        covered = self._find_covered_entities(deduped, uncovered_entities)
        for entity in uncovered_entities:
            if entity not in covered:
                bare_q = f"{entity} {entity_type}"
                bare_norm = bare_q.lower()
                if bare_norm not in seen:
                    seen.add(bare_norm)
                    deduped.append(bare_q)

    async def _generate_targeted_queries(  # noqa: C901, PLR0912
        self,
        gaps: list[tuple[str, str]],
        search_context: str,
        entity_type: str,
        tried_queries: set[str] | None = None,
    ) -> list[str]:
        """Gera queries por entidade a partir dos gaps identificados.

        Estratégia: agrupa gaps por entidade e gera 2-3 queries de perfil completo
        por entidade não coberta. NÃO usa nomes de campos como termos de busca —
        evita desvios causados por nomes de campo que, como termos de busca, têm
        sentido genérico e atraem resultados fora do contexto da entidade.

        Uma página de perfil completo da entidade costuma conter todos os campos
        de uma vez, o que é muito mais eficiente do que uma query por campo.

        tried_queries: conjunto de queries já executadas em rodadas anteriores.
        O LLM é instruído a NÃO repetir essas queries e o output é filtrado contra
        esse conjunto para garantir diversidade entre rodadas.
        """
        # Agrupa campos faltantes por entidade
        entity_gaps: dict[str, list[str]] = {}
        for entity, field in gaps:
            entity_gaps.setdefault(entity, []).append(field)

        uncovered_entities = list(entity_gaps.keys())
        logger.info(
            f"[Queries] {len(uncovered_entities)} entidades com gaps: {uncovered_entities}"
        )

        entities_text = "\n".join(
            f"- {entity} (falta {len(fields)} campo(s))"
            for entity, fields in entity_gaps.items()
        )

        tried_section = ""
        if tried_queries:
            sample = sorted(tried_queries)[:60]
            tried_section = (
                "\nQUERIES JÁ TENTADAS NAS RODADAS ANTERIORES (NÃO repita nenhuma delas):\n"
                + "\n".join(f"  - {q}" for q in sample)
                + "\nGere queries DIFERENTES, usando outros domínios ou termos alternativos.\n"
            )

        prompt = (
            "Você é um especialista em buscas web para coleta de dados estruturados.\n\n"
            f"Tipo de entidade pesquisada: {entity_type}\n"
            f"Contexto: {search_context}\n\n"
            "Para cada entidade abaixo, gere queries que retornem a PÁGINA DE PERFIL "
            "COMPLETO desta entidade em sites especializados.\n"
            "Uma página de perfil/detalhes traz todos os dados de uma vez — é muito mais "
            "eficiente do que buscar campo a campo.\n\n"
            f"Entidades com dados incompletos:\n{entities_text}\n"
            + tried_section
            + "\nREGRAS CRÍTICAS:\n"
            f"- Gere no máximo {max(_MAX_QUERIES_PER_ROUND - len(uncovered_entities), len(uncovered_entities))} queries no total\n"
            "- Use SOMENTE o identificador da entidade nas queries "
            "(o código ou nome próprio que a identifica)\n"
            "- NÃO use os nomes dos campos como palavras de busca — como termos de "
            "busca eles têm sentido genérico e provocam resultados irrelevantes\n"
            "  Ex. ERRADO: 'ENTIDADE campo-a campo-b campo-c'\n"
            "  Ex. CERTO (com site): 'ENTIDADE site:dominio-especializado.com'\n"
            "  Ex. CERTO (sem site): 'ENTIDADE perfil dados completos'\n"
            "- Gere 2-3 queries por entidade variando os domínios especializados\n"
            "- Escolha domínios reconhecidamente especializados neste tipo de entidade\n"
            "- Você PODE usar 'site:' para domínios confiáveis, MAS pelo menos 1 das "
            "queries de cada entidade NÃO deve ter filtro site: — isso permite encontrar "
            "dados em fontes alternativas que os sites principais não cobrem\n"
            "- NÃO repita o mesmo par (entidade, domínio) em queries diferentes\n"
            "- NÃO use aspas, inurl:, intitle:\n\n"
            'Retorne APENAS um JSON: {"queries": ["q1", "q2", ...]}\n\n'
            "Responda APENAS com o JSON, sem texto adicional."
        )
        try:
            response = await self.llm.ainvoke(prompt)
            result = self._parse_llm_json(response)
            queries = result.get("queries", [])[:_MAX_QUERIES_PER_ROUND]
            # Deduplica mantendo ordem e filtra tried_queries
            seen: set[str] = set(tried_queries or set())
            deduped, skipped = self._dedup_queries(queries, seen)
            if skipped:
                logger.info(
                    f"[Queries] {skipped} queries filtradas por já terem sido tentadas"
                )
            self._fill_open_queries(deduped, uncovered_entities, entity_type, seen)
            logger.info(
                f"[Queries] {len(deduped)} queries novas para {len(uncovered_entities)} entidades:"
            )
            for q in deduped:
                logger.info(f"  → {q}")
            return deduped
        except Exception as e:
            logger.warning(f"Erro ao gerar queries direcionadas: {e}")
            # Fallback genérico: uma query por entidade única — sem nomes de campos
            fallback: list[str] = []
            for entity in uncovered_entities[:_MAX_QUERIES_PER_ROUND]:
                q = f"{entity} {entity_type}"
                if not tried_queries or q.lower() not in tried_queries:
                    fallback.append(q)
            return fallback

    @staticmethod
    def _is_placeholder_value(value: object) -> bool:
        """True se o valor extraído é não-informativo (traço, vazio, "não encontrado").

        Marcadores de ausência de dado ocupariam o slot e impediriam uma fonte
        melhor de preenchê-lo (regra "primeiro valor não-nulo vence"). NÃO filtra
        respostas semânticas legítimas como "Não há", "Não há restrição" ou
        "Isento" — só descarta o que claramente não é um dado.
        """
        v = str(value).strip().strip("*").strip()
        if not v:
            return True
        low = v.lower()
        em_dash, en_dash = chr(0x2014), chr(0x2013)  # em dash, en dash
        if low in {
            "-",
            em_dash,
            en_dash,
            "--",
            "---",
            "n/a",
            "na",
            "n.d.",
            "nd",
            "...",
            "-%",
            em_dash + "%",
            "r$ -",
            "r$ " + em_dash,
            "[não encontrado]",
        }:
            return True
        markers = (
            "não encontrado",
            "nao encontrado",
            "não disponível",
            "nao disponivel",
            "ver dados",
            "indeterminado",
            "não há dados",
            "nao ha dados",
            "sem informação",
            "sem informacao",
            "não informado neste",
        )
        return any(m in low for m in markers)

    async def _extract_to_state(  # noqa: PLR0912  # NOSONAR
        self,
        page: dict,
        state: dict[str, dict[str, str | None]],
        required_fields: list[str],
        entity_type: str,
        source_is_snippet: bool = False,
    ) -> int:
        """Extrai dados estruturados de uma página e preenche o estado por entidade.

        Para cada entidade do estado encontrada na página, tenta preencher campos
        ainda vazios. Não sobrescreve campos já preenchidos.

        Retorna o número de campos novos preenchidos nesta chamada.
        """
        content = page.get("content", "")
        url = page.get("url", "")
        if not content.strip():
            return 0

        entities_list = list(state.keys())
        entities_text = ", ".join(entities_list[:30])
        fields_text = "\n".join(f"- {f}" for f in required_fields)
        # Página cheia usa o extract_llm (mini, mais preciso no casamento
        # rótulo↔valor); snippet fica no nano (texto curto, valor frágil e
        # sobrescrevível pela página cheia) para não multiplicar custo.
        if source_is_snippet:
            llm = self.compress_llm or self.llm
        else:
            llm = self.extract_llm or self.compress_llm or self.llm

        prompt = (
            f"Você está analisando o conteúdo de uma página web para extrair "
            f"dados de {entity_type}(s).\n\n"
            f"Entidades de interesse: {entities_text}\n\n"
            f"Campos a extrair para cada entidade encontrada:\n{fields_text}\n\n"
            "Para cada entidade encontrada na página, extraia os valores dos campos listados.\n"
            "REGRAS DE PRECISÃO (siga à risca):\n"
            "1. Use o valor que aparece IMEDIATAMENTE ao lado do rótulo que corresponde "
            "ao campo. Não pegue um número solto só por estar próximo.\n"
            "2. Copie o valor EXATAMENTE como está escrito, incluindo unidade/símbolo "
            "(ex.: %, símbolo de moeda, etc.) e a escala. Não converta, não arredonde, "
            "não recalcule.\n"
            "3. Respeite o escopo/qualificador do campo: se o campo especifica um "
            "período, unidade, recorte ou condição (janela temporal, região, versão, "
            "etc.), pegue o valor que corresponde EXATAMENTE a esse qualificador — NÃO "
            "use um valor de outro recorte, de uma agregação diferente, nem de uma "
            "variante de nome parecido.\n"
            "4. Se houver mais de um candidato e não der para identificar com certeza "
            "qual corresponde ao campo, OMITA o campo — é melhor faltar do que errar.\n"
            "5. Se um campo não estiver presente para uma entidade, omita-o "
            "(não retorne null, não retorne o campo).\n"
            "Use os identificadores exatos das entidades (ex: nome oficial, código, sigla).\n\n"
            'Retorne APENAS um JSON: {"dados": {"ENTIDADE1": {"campo1": "valor1"}, ...}}\n\n'
            f"Fonte: {url}\n\n"
            f"{content}"
        )
        try:
            response = await llm.ainvoke(prompt)
            result = self._parse_llm_json(response)
            dados = result.get("dados", {})

            filled_count = 0
            for entity_key, field_values in dados.items():
                matched_entity = self._match_entity(entity_key, entities_list)
                if matched_entity is None:
                    continue
                for field_key, value in field_values.items():
                    matched_field = self._match_field(field_key, required_fields)
                    if not (matched_field and value):
                        continue
                    # Valor-placeholder não preenche: deixa o slot aberto para uma
                    # fonte melhor (senão "—"/"dados não encontrados" travaria o campo).
                    if self._is_placeholder_value(value):
                        continue
                    existing = state[matched_entity].get(matched_field)
                    # Snippet só preenche campo vazio; conteúdo de página cheia
                    # pode sobrescrever um valor que veio de snippet (mais frágil,
                    # extraído de meta description ruidosa).
                    if existing is not None and not (
                        isinstance(existing, dict)
                        and existing.get("from_snippet")
                        and not source_is_snippet
                    ):
                        continue
                    state[matched_entity][matched_field] = {
                        "valor": str(value),
                        "fonte": url,
                        "from_snippet": source_is_snippet,
                    }
                    if existing is None:
                        filled_count += 1

            if filled_count > 0:
                logger.info(
                    f"[Extração] {url[:70]}: {filled_count} campo(s) preenchido(s)"
                )
            else:
                logger.debug(f"[Extração] {url[:70]}: nenhum campo novo extraído")

            return filled_count

        except Exception as e:
            logger.warning(f"Erro ao extrair dados de {url}: {type(e).__name__}: {e}")
            return 0

    # ------------------------------------------------------------------
    # Fase de descoberta de entidades
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_by_dominant_form(entities: list[str]) -> list[str]:
        """Quando há um grupo relevante de identificadores COMPACTOS (código/sigla de
        token único e curto), descarta os de NOME LONGO — anomalias, tipicamente de um
        tipo diferente que vazou de uma fonte mista.

        Domínio-agnóstico: só dispara quando os códigos compactos formam um grupo
        relevante (>= _MIN_COMPACT_CLUSTER e não a totalidade). Em domínios cujos itens
        são naturalmente nomes longos, não há cluster compacto e nada é filtrado.
        """

        def is_compact(e: str) -> bool:
            s = e.strip()
            return bool(s) and " " not in s and len(s) <= _COMPACT_ID_MAXLEN

        compact = [e for e in entities if is_compact(e)]
        if _MIN_COMPACT_CLUSTER <= len(compact) < len(entities):
            return compact
        return entities

    @staticmethod
    def _count_entities_from_pages(
        discovery_pages: list[dict],
        extraction_results: list[list[str]],
        expected_count: int,
    ) -> dict[str, int]:
        entity_counts: dict[str, int] = {}
        for page, entities in zip(discovery_pages, extraction_results, strict=True):
            unique_in_page = list(
                dict.fromkeys(e.upper().strip() for e in entities if e)
            )
            page_contribution = unique_in_page[:expected_count]
            for entity in page_contribution:
                entity_counts[entity] = entity_counts.get(entity, 0) + 1
            logger.info(
                f"[Descoberta] {page.get('url', '')[:60]}: "
                f"{len(entities)} entidades encontradas | "
                f"{len(page_contribution)} consideradas para ranking"
            )
        return entity_counts

    def _apply_form_filter(self, entity_counts: dict[str, int]) -> dict[str, int]:
        allowed = set(self._filter_by_dominant_form(list(entity_counts.keys())))
        if len(allowed) < len(entity_counts):
            dropped = [e for e in entity_counts if e not in allowed]
            logger.info(
                f"[Descoberta] Filtro de forma: mantidos {len(allowed)} códigos "
                f"compactos; descartados {len(dropped)} nomes longos anômalos: {dropped[:12]}"
            )
            return {e: c for e, c in entity_counts.items() if e in allowed}
        return entity_counts

    def _select_top_entities(
        self, entity_counts: dict[str, int], expected_count: int
    ) -> list[str]:
        ranked = sorted(entity_counts.keys(), key=lambda e: -entity_counts[e])
        min_freq = 2
        high_freq = [e for e in ranked if entity_counts[e] >= min_freq]
        if len(high_freq) >= expected_count:
            selected = high_freq[:expected_count]
        else:
            low_freq = [e for e in ranked if entity_counts[e] < min_freq]
            selected = (high_freq + low_freq)[:expected_count]
        freq_info = {e: entity_counts[e] for e in selected}
        logger.info(
            f"[Descoberta] {len(selected)} entidades selecionadas por frequência: {freq_info}"
        )
        return selected

    async def _discover_entities(
        self,
        discovery_queries: list[str],
        entity_type: str,
        expected_count: int,
        required_fields: list[str],
        visited_urls: set[str],
        all_pages: list[dict],
    ) -> list[str]:
        """Fase 1: coleta páginas de descoberta e extrai os identificadores das entidades.

        Retorna lista de identificadores únicos das entidades (códigos ou nomes).
        """
        if not discovery_queries:
            return []

        logger.info(
            f"[Descoberta] Buscando {expected_count} {entity_type}(s) "
            f"com {len(discovery_queries)} queries de descoberta"
        )

        # Coleta URLs de descoberta (em paralelo)
        all_urls: list[str] = []
        url_to_query: dict[str, str] = {}
        logger.info(
            f"[Descoberta] Executando {len(discovery_queries)} queries em paralelo"
        )
        discovery_search_results = await asyncio.gather(
            *[self._search_searx(q) for q in discovery_queries]
        )
        for q, results in zip(discovery_queries, discovery_search_results, strict=True):
            logger.info(f"[Descoberta] Query: {q} → {len(results)} resultado(s)")
            for result in results:
                url = result.get("url", "")
                if url and url not in url_to_query:
                    url_to_query[url] = q
                    all_urls.append(url)

        filtered, _ = self._filter_urls(all_urls, [], [])
        filtered = [u for u in filtered if not self._is_binary_url(u)]
        # Descoberta crawleia mais páginas que um round normal: páginas de
        # ranking/índice consolidam muitos itens x campos e são a fonte mais densa.
        pool = filtered[
            : self.max_pages * _CRAWL_BUFFER_FACTOR * _DISCOVERY_CRAWL_FACTOR
        ]

        logger.info(
            f"[Descoberta] {len(pool)} URLs para crawl de descoberta "
            f"(de {len(filtered)} aceitas)"
        )

        if not pool:
            return []

        # Dobra temporariamente max_pages para a fase de descoberta: _crawl_pages
        # para em self.max_pages sucessos — sem este override o _DISCOVERY_CRAWL_FACTOR
        # só expande o pool passado mas _crawl_pages ainda limitaria ao max normal.
        original_max = self.max_pages
        self.max_pages = self.max_pages * _DISCOVERY_CRAWL_FACTOR
        try:
            discovery_pages = await self._crawl_pages(
                pool,
                url_to_need_text=url_to_query,
            )
        finally:
            self.max_pages = original_max

        for page in discovery_pages:
            url = page.get("url", "")
            page["query"] = url_to_query.get(url, "")
            visited_urls.add(url)  # só páginas efetivamente crawladas
            all_pages.append(page)

        logger.info(
            f"[Descoberta] {len(discovery_pages)} páginas coletadas — "
            "iniciando extração de entidades"
        )

        # Extrai entidades de cada página (em paralelo)
        extraction_results = await asyncio.gather(
            *[
                self._extract_entity_names(
                    page.get("content", ""),
                    entity_type,
                    expected_count,
                    required_fields,
                )
                for page in discovery_pages
            ]
        )

        entity_counts = self._count_entities_from_pages(
            discovery_pages, extraction_results, expected_count
        )
        entity_counts = self._apply_form_filter(entity_counts)
        return self._select_top_entities(entity_counts, expected_count)

    # ------------------------------------------------------------------
    # Loop principal (override de _arun)
    # ------------------------------------------------------------------

    async def _arun(self, user_request: str) -> list[dict]:  # noqa: PLR0911, PLR0912, PLR0915, C901  # NOSONAR
        logger.info(f"DeepResearchAgent iniciado para: {user_request[:120]}...")

        # Pré-condensação se o request for muito longo
        working_request = user_request
        if self.compress_llm and token_counter(working_request) >= int(
            self.llm_ctx_len * 0.8
        ):
            logger.info(
                f"user_request com ~{token_counter(working_request)} tokens excede 80% "  # NOSONAR
                f"do contexto ({self.llm_ctx_len}) — condensando antes do planejamento."
            )
            working_request = await self._condense_request(working_request)

        # [0] Classificador de modo a montante: por padrão tudo é tratado como busca
        # simples (SearxCrawlAgent); só o modo "deep" segue para a pesquisa profunda.
        classification = await self._classify_search_mode(working_request)
        mode = classification["mode"]

        # Localiza todas as buscas no SearXNG pelo idioma/região do pedido — o
        # _search_searx é compartilhado por todos os modos, então basta ajustar aqui.
        self.search_language = classification["language"]
        logger.info(f"[DeepResearchAgent] Locale de busca: {self.search_language}")

        # Modo single_url: baixa só a página informada, sem buscar. Tratado antes do
        # perfil leve para preservar o Byparr (renderização JS importa numa página só).
        if mode == "single_url":
            return await self._fetch_single_url(
                classification["target_url"], working_request
            )

        # Modo url_search: usa uma URL como referência E consulta outras fontes.
        # Baixa a página-base ANTES de desativar o Byparr (pode depender de render JS);
        # se inacessível, retorna mensagem amigável (a página é a referência do pedido).
        # Caso contrário, roda o perfil leve de busca e antepõe a página-base.
        if mode == "url_search":
            target_url = classification["target_url"]
            logger.info(
                f"[DeepResearchAgent] Modo 'url_search' — referência {target_url} "
                "+ consulta a outras fontes."
            )
            base_page = await self._fetch_page(target_url, "", 0)
            if base_page is None:
                logger.warning(f"[url_search] Página-base inacessível: {target_url}")
                return [
                    {
                        "content": (
                            f"Não foi possível acessar a página de referência "
                            f"{target_url}. O site pode estar indisponível, bloqueando "
                            "acesso automatizado por proteção anti-bot, ou sem conteúdo "
                            "em formato indexável."
                        ),
                        "query": working_request,
                        "references": [],
                    }
                ]
            self.max_rounds = 1
            self.max_pages = min(self.max_pages, 4)
            self.byparr_base_url = ""
            search_results = await super()._arun(user_request)
            base_page["query"] = working_request
            return self._format_results([base_page]) + search_results

        # Modo site_restricted COM URL explícita: o usuário entregou a própria URL do
        # site, então baixa essa página diretamente (fetch-first) e navega seus links
        # internos relevantes — em vez de gastar buscas site: no SearXNG, que dependem
        # dos engines (frequentemente bloqueados) e desperdiçam chamadas. Mantém o
        # Byparr ligado (página/seção do site costuma depender de render JS). Quando
        # vem só o nome do domínio (sem URL), cai no caminho de busca abaixo.
        if mode == "site_restricted" and classification["target_url"]:
            return await self._fetch_site_navigated(
                classification["target_url"],
                classification["allowed_domain"],
                working_request,
            )

        if mode != "deep":
            # Perfil leve para busca não-profunda: uma única passada, poucas páginas e
            # sem fallback headless (Byparr) — que é o maior gargalo de latência quando o
            # fastCRW falha em páginas irrelevantes. A instância do agente é criada por
            # requisição, então ajustar self aqui não afeta outras requisições.
            self.max_rounds = 1
            self.max_pages = min(self.max_pages, 4)
            self.byparr_base_url = ""
            # No modo site_restricted, força o domínio no SearxCrawlAgent — não depende
            # de o _build_search_plan extrair o allowed_urls corretamente.
            if mode == "site_restricted":
                self.forced_allowed_urls = [classification["allowed_domain"]]
            logger.info(
                f"[DeepResearchAgent] Modo '{mode}' — delegando para SearxCrawlAgent "
                f"(perfil leve: max_rounds=1, max_pages={self.max_pages}, byparr off"
                + (
                    f", site:{classification['allowed_domain']}"
                    if mode == "site_restricted"
                    else ""
                )
                + ")."
            )
            return await super()._arun(user_request)

        # [1] Extrai plano de pesquisa profunda
        research_plan = await self._extract_research_plan(working_request)
        required_fields: list[str] = research_plan.get("required_fields") or []
        # Apenas os campos factuais alimentam o loop ReAct (estado/gaps/cobertura).
        # Campos de identidade, calculáveis, autorais e de metadado de fonte ficam
        # de fora da busca e são preenchidos na síntese final pelo LLM de resposta.
        searchable_fields: list[str] = research_plan.get("searchable_fields") or list(
            required_fields
        )
        non_searchable_fields: list[str] = [
            f for f in required_fields if f not in searchable_fields
        ]
        known_entities: list[str] = research_plan.get("known_entities") or []
        expected_count: int = research_plan.get("expected_entity_count") or 1
        discovery_queries: list[str] = research_plan.get("discovery_queries") or []
        entity_type: str = research_plan.get("entity_type") or "entidade"
        search_context: str = research_plan.get("search_context") or working_request

        # Guarda inferior: mesmo classificado como deep, se o plano extraído for trivial
        # (poucos campos/entidades) não compensa o fluxo profundo — delega.
        is_multi_entity = len(required_fields) >= 3 and (
            len(known_entities) >= 3 or expected_count >= 3
        )
        if not is_multi_entity:
            logger.info(
                f"[DeepResearchAgent] Plano trivial "
                f"(entidades={len(known_entities) or expected_count}, "
                f"campos={len(required_fields)}) — delegando para SearxCrawlAgent."
            )
            return await super()._arun(user_request)

        # Calibra parâmetros do loop de acordo com a complexidade do pedido.
        # Pesquisas de porte médio não precisam do esforço máximo — reduz rounds,
        # over-discover e retries de descoberta proporcionalmente.
        complexity = self._compute_complexity(
            len(known_entities) if known_entities else expected_count,
            len(searchable_fields),
        )
        if complexity == "medium":
            effective_max_rounds = _COMPLEXITY_MEDIUM_MAX_ROUNDS
            effective_discover_extra = _COMPLEXITY_MEDIUM_DISCOVER_EXTRA
            effective_discovery_retries = _COMPLEXITY_MEDIUM_RETRIES
        else:  # complex
            effective_max_rounds = self.max_rounds
            effective_discover_extra = _COMPLEXITY_COMPLEX_DISCOVER_EXTRA
            effective_discovery_retries = _MAX_DISCOVERY_RETRIES

        logger.info(
            f"[Plano Deep] Complexidade: {complexity} | "
            f"Tipo: {entity_type} | "
            f"Campos pesquisáveis ({len(searchable_fields)}): {searchable_fields} | "
            f"Não-pesquisáveis ({len(non_searchable_fields)}): {non_searchable_fields} | "
            f"Entidades: {known_entities if known_entities else f'a descobrir (esperadas: {expected_count})'} | "
            f"Parâmetros: max_rounds={effective_max_rounds}, "
            f"over-discover=+{effective_discover_extra}, "
            f"discovery_retries={effective_discovery_retries}"
        )

        all_pages: list[dict] = []
        visited_urls: set[str] = set()
        state: dict[str, dict[str, str | None]] = {}

        # [Fase 1] Determinar as entidades concretas a pesquisar
        if known_entities:
            entities = list(known_entities)
            logger.info(
                f"[Plano Deep] Entidades conhecidas ({len(entities)}): {entities}"
            )
        else:
            # Over-discover: descobre um pool MAIOR que o pedido porque parte dos
            # candidatos será de tipo errado (catálogos mistos listam outros tipos) e
            # cairá na poda por evidência adiante. O tamanho do buffer é proporcional
            # à complexidade: pesquisas complexas têm mais ruído e precisam de mais
            # margem; pesquisas médias têm menos candidatos espúrios.
            discover_target = min(
                expected_count + effective_discover_extra, _MAX_DISCOVER_POOL
            )
            logger.info(
                f"[Fase 1/Descoberta] Descobrindo até {discover_target} {entity_type}(s) "
                f"(meta final: {expected_count}; buffer +{effective_discover_extra} "
                f"cai na poda por evidência)..."
            )
            entities = await self._discover_entities(
                discovery_queries,
                entity_type,
                discover_target,
                searchable_fields,
                visited_urls,
                all_pages,
            )
            # Descoberta iterativa: se a recall ficou abaixo do pool-alvo, o agente
            # reflete e refaz a busca com queries mais amplas (voltadas a listas),
            # acumulando candidatos — em vez de seguir com poucas entidades.
            discovery_attempt = 0
            while (
                len(entities) < discover_target
                and discovery_attempt < effective_discovery_retries
            ):
                discovery_attempt += 1
                logger.info(
                    f"[Descoberta] Recall baixa: {len(entities)}/{discover_target} "
                    f"entidades. Tentativa adicional {discovery_attempt}/"
                    f"{effective_discovery_retries} com queries mais amplas."
                )
                extra_queries = await self._generate_broader_discovery_queries(
                    entity_type,
                    search_context,
                    entities,
                    discover_target - len(entities),
                )
                if not extra_queries:
                    break
                more = await self._discover_entities(
                    extra_queries,
                    entity_type,
                    discover_target,
                    searchable_fields,
                    visited_urls,
                    all_pages,
                )
                before = len(entities)
                for e in more:
                    if e not in entities:
                        entities.append(e)
                entities = entities[:discover_target]
                if len(entities) == before:
                    logger.info(
                        "[Descoberta] Tentativa adicional não trouxe novas "
                        "entidades — encerrando descoberta."
                    )
                    break

            if not entities:
                logger.warning(
                    "[Fase 1] Nenhuma entidade descoberta — "
                    "delegando para SearxCrawlAgent."
                )
                return await super()._arun(user_request)

        # Inicializa estado apenas com os campos pesquisáveis
        for entity in entities:
            state[entity] = dict.fromkeys(searchable_fields, None)

        total_slots = len(entities) * len(searchable_fields)
        logger.info(
            f"[Estado] Inicializado: {len(entities)} entidades x "
            f"{len(searchable_fields)} campos pesquisáveis = {total_slots} slots a preencher"
        )

        # Pré-extrai dados das páginas de descoberta para o estado.
        # As páginas já foram crawladas — aproveita o conteúdo sem re-crawl.
        # Neste ponto active_fields == searchable_fields (nenhum abandonado ainda).
        if all_pages:
            logger.info(
                f"[Pré-extração] Extraindo estado de {len(all_pages)} páginas de descoberta"
            )
            await asyncio.gather(
                *[
                    self._extract_to_state(page, state, searchable_fields, entity_type)
                    for page in all_pages
                ]
            )

        self._log_progress(state, searchable_fields, round_num=0)

        # [Fase 2] Loop ReAct de pesquisa por entidade/campo
        tried_queries: set[str] = set()  # queries já executadas em rodadas anteriores
        field_no_fill_rounds: dict[str, int] = dict.fromkeys(searchable_fields, 0)
        deprioritized_fields: set[str] = set()

        for round_num in range(1, effective_max_rounds + 1):
            # S5: campos inacessíveis são excluídos do cálculo de cobertura e gaps
            active_fields = [
                f for f in searchable_fields if f not in deprioritized_fields
            ]

            gaps = self._identify_gaps(state, active_fields)

            if not gaps:
                logger.info(f"[Round {round_num}] Todos os campos preenchidos!")
                break

            if self._check_coverage(state, active_fields):
                logger.info(
                    f"[Round {round_num}] Cobertura suficiente atingida "  # NOSONAR
                    f"({self.coverage_entities_threshold * 100:.0f}% de entidades "
                    f"com ≥{self.coverage_fields_threshold * 100:.0f}% campos) — encerrando."
                )
                break

            logger.info(
                f"[Round {round_num}/{effective_max_rounds}] "
                f"{len(gaps)} gaps a preencher em {len(state)} entidades"
            )

            # S1: snapshot de fills por campo antes desta rodada
            fills_before = {
                f: sum(1 for e in state if state[e].get(f) is not None)
                for f in searchable_fields
            }

            # [3] Gera queries cirúrgicas para os gaps (excluindo tried_queries)
            queries = await self._generate_targeted_queries(
                gaps, search_context, entity_type, tried_queries
            )

            if not queries:
                logger.info(
                    f"[Round {round_num}] Sem queries novas — encerrando pesquisa."
                )
                break

            # Acumula tried_queries para rodadas futuras
            tried_queries.update(q.strip().lower() for q in queries)

            # [4] Busca no SearXNG (em paralelo)
            all_urls: list[str] = []
            url_to_query: dict[str, str] = {}
            url_to_snippet: dict[str, str] = {}
            search_results_list = await asyncio.gather(
                *[self._search_searx(q) for q in queries]
            )
            for q, results in zip(queries, search_results_list, strict=True):
                for result in results:
                    url = result.get("url", "")
                    if url and url not in visited_urls and url not in url_to_query:
                        url_to_query[url] = q
                        all_urls.append(url)
                        snippet = result.get("snippet", "").strip()
                        if snippet:
                            url_to_snippet[url] = snippet

            # [4.5] Extrai campos diretamente dos snippets antes do crawl completo.
            # Fontes especializadas frequentemente já expõem valores-chave no
            # meta description / snippet de resultado. Os valores extraídos do
            # snippet são frágeis (texto curto e ruidoso) e marcados como tal: a
            # página cheia, quando crawlada, pode sobrescrevê-los. O snippet NÃO
            # dispensa mais o crawl — fazia páginas densas (com todos os campos)
            # serem descartadas só porque 1 campo veio do snippet.
            snippet_source_pages: list[dict] = []
            if url_to_snippet and active_fields:
                # Ordena snippets: primeiro de domínios que já produziram
                # extrações em rounds anteriores, depois os demais.
                _snippet_items = list(url_to_snippet.items())
                _productive_domains = {
                    url.split("/")[2] if "://" in url else url for url in url_to_snippet
                } & set()  # será populado pelos snippets que já extraíram
                _snippet_items.sort(
                    key=lambda x, _pd=_productive_domains: (
                        x[0].split("/")[2] if "://" in x[0] else x[0]
                    )
                    not in _pd,
                )
                # Limita a 100 snippets por round para evitar gargalo
                _MAX_SNIPPETS_PER_ROUND = 100
                snippet_pages = []
                for url, snippet in _snippet_items[:_MAX_SNIPPETS_PER_ROUND]:
                    snippet_pages.append(
                        {
                            "url": url,
                            "content": snippet,
                            "query": url_to_query.get(url, ""),
                            "title": "",
                            "source": "snippet",
                        }
                    )
                snippet_fill_results = await asyncio.gather(
                    *[
                        self._extract_to_state(
                            page,
                            state,
                            active_fields,
                            entity_type,
                            source_is_snippet=True,
                        )
                        for page in snippet_pages
                    ]
                )
                # URLs com fill por snippet são registradas como fonte só DEPOIS
                # do crawl (deferido em snippet_source_pages), para a página cheia
                # vencer o idx/hover de citação. Não marca visited → segue ao crawl.
                for page, filled in zip(
                    snippet_pages, snippet_fill_results, strict=True
                ):
                    if filled > 0:
                        snippet_source_pages.append(page)
                logger.info(
                    f"[Round {round_num}] Snippets: {len(snippet_pages)} analisados "
                    f"(de {len(url_to_snippet)} disponíveis, "
                    f"limite={_MAX_SNIPPETS_PER_ROUND}) | "
                    f"{sum(snippet_fill_results)} campo(s) extraídos "
                    "(crawl não dispensado)"
                )

            # [5] Filtra e monta pool de crawl.
            # Exclui URLs já resolvidas por snippet (visited_urls atualizado acima).
            filtered, _ = self._filter_urls(all_urls, [], [])
            filtered = [
                u
                for u in filtered
                if not self._is_binary_url(u) and u not in visited_urls
            ]
            pool = filtered[: self.max_pages * _CRAWL_BUFFER_FACTOR]

            logger.info(
                f"[Round {round_num}] URLs: {len(all_urls)} encontradas | "
                f"{len(filtered)} aceitas | {len(pool)} no pool de crawl "
                f"({len(url_to_snippet)} com snippet)"
            )

            if not pool:
                logger.info(f"[Round {round_num}] Pool vazio — encerrando pesquisa.")
                break

            # [6] Coleta conteúdo das páginas via fastCRW. Marca como visitadas só
            # as URLs efetivamente tentadas (attempted) — as canceladas ao atingir
            # max_pages voltam ao pool em rounds seguintes. Antes, marcar o pool
            # inteiro antes do crawl queimava as páginas densas (lentas) que perdem
            # a corrida do as_completed para páginas leves e nunca eram re-tentadas.
            attempted: set[str] = set()
            crawled = await self._crawl_pages(
                pool, url_to_need_text=url_to_query, attempted_out=attempted
            )
            visited_urls.update(attempted)

            crawled_urls = {p.get("url", "") for p in crawled}
            for page in crawled:
                url = page.get("url", "")
                page["query"] = url_to_query.get(url, "")
                all_pages.append(page)
            # Registra agora as fontes que só tiveram fill por snippet e cuja
            # página cheia não foi crawlada — a crawlada já entrou acima e vence
            # o idx/hover de citação por dedup de URL.
            for page in snippet_source_pages:
                if page.get("url", "") not in crawled_urls:
                    all_pages.append(page)

            logger.info(
                f"[Round {round_num}] {len(crawled)} página(s) coletadas com conteúdo real "
                f"(de {len(attempted)} tentadas, {len(pool)} no pool) | "
                f"total acumulado: {len(all_pages)}"
            )

            # [7] Extrai dados de cada página e preenche o estado (em paralelo)
            # Usa active_fields — campos deprioritized são ignorados.
            if crawled:
                await asyncio.gather(
                    *[
                        self._extract_to_state(page, state, active_fields, entity_type)
                        for page in crawled
                    ]
                )

            # S1: atualiza contadores de rounds sem extração por campo
            for f in searchable_fields:
                if f in deprioritized_fields:
                    continue
                new_fills = sum(1 for e in state if state[e].get(f) is not None)
                if new_fills > fills_before[f]:
                    field_no_fill_rounds[f] = 0  # progresso → zera contador
                else:
                    field_no_fill_rounds[f] += 1
                    if field_no_fill_rounds[f] >= _MAX_FIELD_EMPTY_ROUNDS:
                        deprioritized_fields.add(f)
                        logger.info(
                            f"[Campo abandonado] '{f}': {_MAX_FIELD_EMPTY_ROUNDS} rounds "
                            "consecutivos sem extração — excluído dos próximos gaps"
                        )

            # [log] Progresso após extração desta rodada
            self._log_progress(state, searchable_fields, round_num)

        # [7.5] Poda por evidência (só quando houve over-discover): quem é do tipo
        # preenche os campos discriminantes; quem não é (veio de catálogo misto)
        # fica com pouquíssimos campos por mais que se busque. Descarta os de baixa
        # evidência e mantém os expected_count mais completos — sem conhecimento de
        # domínio, o próprio dado coletado separa instância real de ruído de tipo.
        if not known_entities and len(state) > expected_count:
            fill = {
                e: sum(1 for v in state[e].values() if v is not None) for e in state
            }
            # Piso baixo de plausibilidade: descarta o que não é instância (índices,
            # agregados, stragglers com ~0 dado). Acima do piso, mantém os
            # expected_count MAIS completos — o filtro de forma já removeu o ruído de
            # tipo, então o pool restante é de instâncias reais; aqui só preferimos as
            # mais bem documentadas, preservando os slots para a meta do usuário.
            floor = max(2, len(searchable_fields) // 4)
            qualified = sorted(
                (e for e in state if fill[e] >= floor), key=lambda e: -fill[e]
            )
            kept = qualified[:expected_count]
            if kept:
                dropped = [e for e in state if e not in kept]
                logger.info(
                    f"[Poda] Mantidas {len(kept)} entidades mais completas "
                    f"(piso {floor} campos); descartadas {len(dropped)}: {dropped}"
                )
                state = {e: state[e] for e in kept}
            else:
                logger.info("[Poda] Nenhuma entidade acima do piso — mantendo todas.")

        # [8] Registro de fontes: cada URL-fonte única recebe um idx de citação
        # <web_N> estável (idx começa em 2; o item agregado é o idx 1). O mesmo idx
        # anota cada dado no conteúdo agregado como (fonte: <web_N>) — que o LLM
        # reproduz como citação — e identifica a referência (url + trecho) consumida
        # pelo tooltip de hover e pela seção "Referências".
        url_to_idx: dict[str, int] = {}
        source_items: list[dict] = []
        next_idx = 2
        for page in all_pages:
            url = page.get("url", "")
            if not url or url in url_to_idx:
                continue
            url_to_idx[url] = next_idx
            source_items.append(
                {
                    "content": "",
                    "query": "",  # sem query → não gera <busca_N> vazio no contexto
                    "idx": next_idx,
                    "references": [
                        {
                            "url": url,
                            "title": page.get("title", ""),
                            # trecho da página, base do tooltip de hover (não vai ao LLM)
                            "snippet": (page.get("content") or "").strip(),
                        }
                    ],
                }
            )
            next_idx += 1

        # Agrega estado em conteúdo estruturado, anotando as fontes com <web_N>.
        aggregated_content = self._aggregate_state(
            state, searchable_fields, non_searchable_fields, url_to_idx
        )
        logger.info(
            f"[Agregação] Estado compilado: {len(aggregated_content)} chars, "
            f"{len(all_pages)} páginas consultadas, {len(url_to_idx)} fontes citáveis"
        )

        # Estado agregado primeiro (idx 1); páginas-fonte como itens de referência
        # (content="") — preserva a associação idx↔url sem passar o conteúdo bruto
        # ao LLM de síntese, evitando ContextWindowExceeded.
        results = [
            {
                "content": aggregated_content,
                "query": search_context,
                "references": [],
                "node": "deep_research_aggregated",
                "idx": 1,
            },
        ]
        results.extend(source_items)
        return results
