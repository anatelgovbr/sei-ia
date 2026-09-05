from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from ._protocol import _ClientInternals

    _Base = _ClientInternals
else:
    _Base = object

logger = logging.getLogger(__name__)

_PROCESS_METADATA_COLUMNS = [
    "id_protocolo",
    "protocolo_formatado",
    "processo_especificacao",
    "interessado",
    "name_interested",
    "processos_relacionados_1",
    "processos_relacionados_2",
    "id_type_process",
    "id_unit_process_generator",
    "name_id_unit_process_generator",
    "name_id_type_process",
]


def _build_processo_linhas(data: dict, base: dict) -> list[dict]:
    """Expand one API record into one or more rows based on parent/child relationships.

    Args:
        data: Raw API dict for a single procedimento.
        base: Fields shared across all expanded rows for this procedimento.

    Returns:
        List of row dicts, each adding ``rp1p_descricao``, ``rp2p_descricao``,
        ``rp1u_sigla``, ``rp2u_sigla`` to ``base``.
    """
    processos_pai = data.get("ProcessosPaiRelacionado") or []
    processos_filho = data.get("ProcessosFilhoRelacionado") or []
    if processos_pai and processos_filho:
        return [
            {
                **base,
                "rp1p_descricao": pai.get("Especificacao") or "",
                "rp2p_descricao": filho.get("Especificacao") or "",
                "rp1u_sigla": pai.get("SiglaUnidadeGeradoraProcesso") or "",
                "rp2u_sigla": filho.get("SiglaUnidadeGeradoraProcesso") or "",
            }
            for pai in processos_pai
            for filho in processos_filho
        ]
    if processos_pai:
        return [
            {
                **base,
                "rp1p_descricao": pai.get("Especificacao") or "",
                "rp2p_descricao": "",
                "rp1u_sigla": pai.get("SiglaUnidadeGeradoraProcesso") or "",
                "rp2u_sigla": "",
            }
            for pai in processos_pai
        ]
    if processos_filho:
        return [
            {
                **base,
                "rp1p_descricao": "",
                "rp2p_descricao": filho.get("Especificacao") or "",
                "rp1u_sigla": "",
                "rp2u_sigla": filho.get("SiglaUnidadeGeradoraProcesso") or "",
            }
            for filho in processos_filho
        ]
    return [
        {
            **base,
            "rp1p_descricao": "",
            "rp2p_descricao": "",
            "rp1u_sigla": "",
            "rp2u_sigla": "",
        }
    ]


def _parse_process_metadata(api_dicts: list[dict]) -> pd.DataFrame:
    """Parse a list of md_ia_consulta_processo records into process-metadata rows.

    Each record is expanded by ``IdProcessosAnexados``: one row per attached
    process ID, or a single row with ``processos_relacionados_1=None`` when the
    list is empty.

    Args:
        api_dicts: ``data`` list from the API JSON response.

    Returns:
        DataFrame with columns ``_PROCESS_METADATA_COLUMNS``.
    """
    records: list[dict] = []
    for api_dict in api_dicts:
        processos_anexados = api_dict.get("IdProcessosAnexados") or []
        processos_pai = api_dict.get("ProcessosPaiRelacionado") or []
        descricao_pai = "; ".join(p.get("Especificacao") or "" for p in processos_pai)
        interessados = api_dict.get("Interessados") or []
        interessado_id = interessados[0]["IdInteressado"] if interessados else None
        interessado_nome = (
            interessados[0].get("NomeInteressado") if interessados else None
        )
        base = {
            "id_protocolo": api_dict["IdProcedimento"],
            "protocolo_formatado": api_dict["NumeroProcesso"],
            "processo_especificacao": api_dict["EspecificacaoProcesso"]
            or api_dict["TipoProcesso"],
            "interessado": interessado_id,
            "name_interested": interessado_nome,
            "processos_relacionados_2": descricao_pai,
            "id_type_process": api_dict["IdTipoProcesso"],
            "id_unit_process_generator": api_dict["IdUnidadeGeradoraProcesso"],
            "name_id_unit_process_generator": api_dict.get(
                "DescricaoUnidadeGeradoraProcesso"
            ),
            "name_id_type_process": api_dict["TipoProcesso"],
        }
        if processos_anexados:
            for proc_rel in processos_anexados:
                records.append({**base, "processos_relacionados_1": int(proc_rel)})
        else:
            records.append({**base, "processos_relacionados_1": None})
    return pd.DataFrame(records, columns=_PROCESS_METADATA_COLUMNS)


class ProcessesMixin(_Base):
    """Sync process endpoints for the SEI API client."""

    def md_ia_consulta_processo(self, id_procedimentos: str) -> pd.DataFrame:
        """Fetch process metadata and related-process relationships.

        Sends ``SinFiltraAtivos=N``, ``SinFiltraBloqueados=N``, and
        ``SinFiltraDocumentosRelevantes=N`` (assist superset). Each API record
        is expanded by ``_build_processo_linhas``: one row per pai×filho pair,
        one row per pai/filho alone, or a single baseline row when neither
        list is present.

        Args:
            id_procedimentos: Comma-separated procedure IDs.

        Returns:
            DataFrame with columns ``id_procedimento``,
            ``id_protocolo_formatado``, ``processo_especificacao``,
            ``nome_id_tipo_processo``, ``rp1p_descricao``, ``rp2p_descricao``,
            ``rp1u_sigla``, ``rp2u_sigla``, ``sigla_unid``, ``desc_unid``.
        """
        service_endpoint = "md_ia_consulta_processo"
        payload = self._request_json(
            service_endpoint,
            extra_params={
                "SinFiltraAtivos": "N",
                "SinFiltraBloqueados": "N",
                "SinFiltraDocumentosRelevantes": "N",
                "IdProcedimentos": id_procedimentos,
            },
            document_id_hint=str(id_procedimentos),
        )
        data_list = payload.get("data") or []
        rows: list[dict] = []
        for data in data_list:
            base = {
                "id_procedimento": data.get("IdProcedimento"),
                "id_protocolo_formatado": data.get("NumeroProcesso") or "",
                "processo_especificacao": data.get("EspecificacaoProcesso") or "",
                "nome_id_tipo_processo": data.get("TipoProcesso") or "",
                "sigla_unid": data.get("SiglaUnidadeGeradoraProcesso") or "",
                "desc_unid": data.get("DescricaoUnidadeGeradoraProcesso") or "",
            }
            rows.extend(_build_processo_linhas(data, base))
        return pd.DataFrame(rows)

    def md_ia_consulta_processo_metadados(
        self, id_procedimento: str, chunk_size: int | None = None
    ) -> pd.DataFrame:
        """Fetch rich process metadata including related-process IDs and parent descriptions.

        Chunks ``id_procedimento`` by ``chunk_size`` (defaults to
        ``self.config.chunk_size``). Each chunk is fetched with a single
        ``_request_json`` call. Records are expanded by ``_parse_process_metadata``:
        one row per ``IdProcessosAnexados`` entry, or one row with
        ``processos_relacionados_1=None`` when the list is absent.

        Args:
            id_procedimento: Comma-separated procedure IDs.
            chunk_size: Override for the per-request batch size.

        Returns:
            DataFrame with columns ``_PROCESS_METADATA_COLUMNS``.
        """
        service_endpoint = "md_ia_consulta_processo"
        effective_chunk = (
            chunk_size if chunk_size is not None else self.config.chunk_size
        )
        id_list = [i.strip() for i in str(id_procedimento).split(",") if i.strip()]
        all_dfs: list[pd.DataFrame] = []

        for i in range(0, len(id_list), effective_chunk):
            chunk = ",".join(id_list[i : i + effective_chunk])
            payload = self._request_json(
                service_endpoint,
                extra_params={"IdProcedimentos": chunk},
                document_id_hint=chunk,
            )
            api_dicts = payload.get("data") or []
            if api_dicts:
                df_chunk = _parse_process_metadata(api_dicts)
                if not df_chunk.empty:
                    all_dfs.append(df_chunk)

        if not all_dfs:
            return pd.DataFrame(columns=_PROCESS_METADATA_COLUMNS)
        return pd.concat(all_dfs, ignore_index=True)
