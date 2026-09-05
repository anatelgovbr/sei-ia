"""Processador final de stream para substituir tags de citação em tempo real."""

import logging
import re

from sei_ia.agents.rag.sources import (
    _collect_web_reference_entries,
    build_web_references_section,
    create_chunk_tooltip,
    create_doc_tooltip,
    create_upload_tooltip,
    create_web_search_tooltip,
    find_chunk_metadata,
    find_web_search_metadata,
    get_document_count,
)
from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.pydantic_models import UserState

setup_logging()
logger = logging.getLogger(__name__)


class StreamTagProcessorFinal:
    """Processa tags de citação durante o streaming token-by-token."""

    def __init__(self, user_state: UserState):
        """Inicializa o processador com o estado do usuário.

        Args:
            user_state: Estado com metadados dos chunks, documentos e web search
        """
        self.user_state = user_state
        self.accumulator = ""  # Acumula todo o conteúdo
        self.doc_count = get_document_count(user_state)
        # Numeração sequencial global para todos os tipos de fontes
        self.next_sequential_number = 1
        # Mapear chunks para numeração sequencial: {(doc_id, chunk_idx): sequential_number}
        self.chunk_sequential_map = {}
        # Mapear documentos para numeração sequencial: {doc_id: sequential_number}
        self.doc_sequential_map = {}
        # Mapear uploads para numeração sequencial: {upload_id: sequential_number}
        self.upload_sequential_map = {}
        # Mapear web search para numeração sequencial: {idx: sequential_number}
        self.web_sequential_map = {}

    def process_token(self, token: str) -> str:
        """Processa um token do stream.

        Args:
            token: Token recebido do stream

        Returns:
            String a ser impressa (pode ser vazia se acumulando tag)
        """
        # Adiciona token ao acumulador
        self.accumulator += token

        # Se o token termina com '>', pode ser fim de uma tag - força processamento
        if token.endswith(">"):
            return self._process_accumulated()

        # Se não há tags incompletas, pode liberar o conteúdo
        if not self._has_incomplete_tag():
            return self._process_accumulated()

        # Tag incompleta - continue acumulando
        return ""

    def _process_accumulated(  # noqa: C901, PLR0912, PLR0915  # NOSONAR
        self,
    ) -> str:
        """Processa todo o conteúdo acumulado em busca de tags.

        Returns:
            String processada (com tags substituídas)
        """
        if not self.accumulator:
            return ""

        output = ""

        while True:
            # Buscar por tags de chunk: <doc_ID_INDEX></doc_ID_INDEX>
            chunk_match = re.search(
                r"<doc_(\d+)_(\d+)></doc_(\d+)_(\d+)>", self.accumulator
            )

            if chunk_match:
                doc_id_open, chunk_idx, doc_id_close, chunk_idx_close = (
                    chunk_match.groups()
                )

                # Verificar se é uma tag válida (abertura e fechamento coincidem)
                if doc_id_open == doc_id_close and chunk_idx == chunk_idx_close:
                    tag_start = chunk_match.start()
                    tag_end = chunk_match.end()

                    # Emite tudo antes da tag
                    before_tag = self.accumulator[:tag_start]
                    output += before_tag

                    # Gerar número sequencial para o usuário
                    chunk_key = (doc_id_open, chunk_idx)
                    if chunk_key not in self.chunk_sequential_map:
                        self.chunk_sequential_map[chunk_key] = (
                            self.next_sequential_number
                        )
                        self.next_sequential_number += 1

                    sequential_number = self.chunk_sequential_map[chunk_key]

                    # Substitui a tag pelo tooltip
                    chunk_metadata = find_chunk_metadata(
                        chunk_idx, doc_id_open, self.user_state
                    )
                    if chunk_metadata:
                        # Usar numeração sequencial ao invés do chunk_index original
                        tooltip = create_chunk_tooltip(
                            chunk_metadata, sequential_number
                        )
                        output += tooltip
                    else:
                        # Se não encontrar metadados, usar numeração sequencial
                        output += f"[{sequential_number}]"

                    # Remove do acumulador o que já foi processado (incluindo a tag)
                    self.accumulator = self.accumulator[tag_end:]
                    continue

            # Buscar por tags de documento: <doc_ID></doc_ID>
            doc_match = re.search(r"<doc_(\d+)></doc_(\d+)>", self.accumulator)

            if doc_match:
                doc_id_open, doc_id_close = doc_match.groups()

                # Verificar se é uma tag válida (abertura e fechamento coincidem)
                if doc_id_open == doc_id_close:
                    tag_start = doc_match.start()
                    tag_end = doc_match.end()
                    doc_id = doc_id_open

                    # Emite tudo antes da tag
                    before_tag = self.accumulator[:tag_start]
                    output += before_tag

                    # Gerar número sequencial global para o documento
                    if doc_id not in self.doc_sequential_map:
                        self.doc_sequential_map[doc_id] = self.next_sequential_number
                        self.next_sequential_number += 1

                    sequential_number = self.doc_sequential_map[doc_id]

                    # Obter somente o identificador visível. O ID cru é necessário
                    # para localizar a tag, mas nunca pode virar texto de frontend
                    # quando o número SEI não estiver disponível.
                    id_to_formatted_map = self.user_state.get("id_to_formatted_map", {})
                    doc_id_formatado = id_to_formatted_map.get(doc_id)
                    if not doc_id_formatado:
                        logger.warning(
                            "Número SEI não encontrado para a fonte do documento %s",
                            doc_id,
                        )

                    tooltip = create_doc_tooltip(
                        doc_id, doc_id_formatado, sequential_number, self.doc_count
                    )
                    output += tooltip

                    # Remove do acumulador o que já foi processado (incluindo a tag)
                    self.accumulator = self.accumulator[tag_end:]
                    continue

            # Buscar por tags de upload: <upload_ID></upload_ID>
            upload_match = re.search(r"<upload_(\d+)></upload_(\d+)>", self.accumulator)

            if upload_match:
                upload_id_open, upload_id_close = upload_match.groups()

                # Verificar se é uma tag válida (abertura e fechamento coincidem)
                if upload_id_open == upload_id_close:
                    tag_start = upload_match.start()
                    tag_end = upload_match.end()
                    upload_id = upload_id_open

                    # Emite tudo antes da tag
                    before_tag = self.accumulator[:tag_start]
                    output += before_tag

                    # Só uploads materializados com sucesso podem gerar fonte.
                    upload_id_to_filename_map = self.user_state.get(
                        "upload_id_to_filename_map", {}
                    )
                    filename = upload_id_to_filename_map.get(upload_id)
                    if filename:
                        if upload_id not in self.upload_sequential_map:
                            self.upload_sequential_map[upload_id] = (
                                self.next_sequential_number
                            )
                            self.next_sequential_number += 1

                        sequential_number = self.upload_sequential_map[upload_id]
                        output += create_upload_tooltip(filename, sequential_number)
                    else:
                        logger.warning(
                            "Arquivo enviado não encontrado para a fonte do upload %s",
                            upload_id,
                        )

                    # Remove do acumulador o que já foi processado (incluindo a tag)
                    self.accumulator = self.accumulator[tag_end:]
                    continue

            # Buscar por tags de web search: <web_N> (sem fechamento obrigatório)
            web_match = re.search(r"<web_(\d+)>", self.accumulator)

            if web_match:
                web_idx = web_match.group(1)
                tag_start = web_match.start()
                tag_end = web_match.end()

                # Emite tudo antes da tag
                before_tag = self.accumulator[:tag_start]
                output += before_tag

                # Gerar número sequencial global para web search
                if web_idx not in self.web_sequential_map:
                    self.web_sequential_map[web_idx] = self.next_sequential_number
                    self.next_sequential_number += 1

                sequential_number = self.web_sequential_map[web_idx]

                # Buscar metadados do web search
                metadata = find_web_search_metadata(web_idx, self.user_state)

                if metadata:
                    tooltip = create_web_search_tooltip(metadata, sequential_number)
                    output += tooltip
                else:
                    # Fallback: usar número sequencial sem link
                    logger.warning(
                        f"Metadados não encontrados para web_search idx={web_idx}"
                    )
                    output += f"[{sequential_number}]"

                # Remove do acumulador o que já foi processado (incluindo a tag)
                self.accumulator = self.accumulator[tag_end:]
                continue

            # Limpar tags de fechamento soltas </web_N> que possam existir
            web_close_match = re.search(r"</web_\d+>", self.accumulator)
            if web_close_match:
                # Remove a tag de fechamento
                self.accumulator = (
                    self.accumulator[: web_close_match.start()]
                    + self.accumulator[web_close_match.end() :]
                )
                continue

            # Não há mais tags - liberar o resto
            if not self._has_incomplete_tag():
                output += self.accumulator
                self.accumulator = ""
            return output

    def _has_incomplete_tag(self) -> bool:
        """Verifica se o acumulador tem uma tag incompleta.

        Returns:
            True se houver tag incompleta
        """
        # Se há qualquer '<' no acumulador que não foi processado como tag completa,
        # considerar como tag incompleta para aguardar mais tokens
        if "<" in self.accumulator:
            # Verifica se pode ser início de uma tag doc, upload ou web
            if (
                self.accumulator.endswith("<")
                or self.accumulator.endswith("<d")
                or self.accumulator.endswith("<do")
                or self.accumulator.endswith("<doc")
                or self.accumulator.endswith("<u")
                or self.accumulator.endswith("<up")
                or self.accumulator.endswith("<upl")
                or self.accumulator.endswith("<uplo")
                or self.accumulator.endswith("<uploa")
                or self.accumulator.endswith("<upload")
                or self.accumulator.endswith("<w")
                or self.accumulator.endswith("<we")
                or self.accumulator.endswith("<web")
            ):
                return True

            # Verifica padrões específicos de tags incompletas
            incomplete_patterns = [
                # Padrões para tags de chunk: <doc_ID_INDEX></doc_ID_INDEX>
                r"<doc_\d*$",  # <doc_123 (parcial)
                r"<doc_\d+_$",  # <doc_123_
                r"<doc_\d+_\d*$",  # <doc_123_45 (parcial)
                r"<doc_\d+_\d+>$",  # <doc_123_456> (só abertura)
                r"<doc_\d+_\d+><$",  # <doc_123_456><
                r"<doc_\d+_\d+></$",  # <doc_123_456></
                r"<doc_\d+_\d+></d*$",  # <doc_123_456></d (parcial)
                r"<doc_\d+_\d+></doc*$",  # <doc_123_456></doc (parcial)
                r"<doc_\d+_\d+></doc_$",  # <doc_123_456></doc_
                r"<doc_\d+_\d+></doc_\d*$",  # <doc_123_456></doc_123 (parcial)
                r"<doc_\d+_\d+></doc_\d+_$",  # <doc_123_456></doc_123_
                r"<doc_\d+_\d+></doc_\d+_\d*$",  # <doc_123_456></doc_123_45 (parcial)
                # Padrões para tags de documento simples: <doc_ID></doc_ID>
                r"<doc_\d+>$",  # <doc_123> (só abertura)
                r"<doc_\d+><$",  # <doc_123><
                r"<doc_\d+></$",  # <doc_123></
                r"<doc_\d+></d*$",  # <doc_123></d (parcial)
                r"<doc_\d+></doc*$",  # <doc_123></doc (parcial)
                r"<doc_\d+></doc_$",  # <doc_123></doc_
                r"<doc_\d+></doc_\d*$",  # <doc_123></doc_12 (parcial)
                # Padrões para tags de upload: <upload_ID></upload_ID>
                r"<upload_$",  # <upload_ (parcial)
                r"<upload_\d*$",  # <upload_123 (parcial)
                r"<upload_\d+>$",  # <upload_123> (só abertura)
                r"<upload_\d+><$",  # <upload_123><
                r"<upload_\d+></$",  # <upload_123></
                r"<upload_\d+></u*$",  # <upload_123></u (parcial)
                r"<upload_\d+></up*$",  # <upload_123></up (parcial)
                r"<upload_\d+></upl*$",  # <upload_123></upl (parcial)
                r"<upload_\d+></uplo*$",  # <upload_123></uplo (parcial)
                r"<upload_\d+></uploa*$",  # <upload_123></uploa (parcial)
                r"<upload_\d+></upload*$",  # <upload_123></upload (parcial)
                r"<upload_\d+></upload_$",  # <upload_123></upload_
                r"<upload_\d+></upload_\d*$",  # <upload_123></upload_12
                # Padrões para tags de web search: <web_N>
                r"<web_$",  # <web_ (parcial)
                r"<web_\d*$",  # <web_1 (parcial, sem fechamento >)
            ]

            for pattern in incomplete_patterns:
                if re.search(pattern, self.accumulator):
                    return True

        return False

    def flush(self) -> str:
        """Retorna qualquer conteúdo pendente, seguido da seção "Referências".

        A seção lista [N]: url das fontes web citadas. É montada aqui, no fim do
        stream, quando web_sequential_map já está completo. Sem marcadores web,
        nenhuma seção é anexada.

        Returns:
            Conteúdo final restante + seção de referências (quando houver)
        """
        output = ""
        if self.accumulator:
            output = self.accumulator
            self.accumulator = ""

        section = build_web_references_section(
            _collect_web_reference_entries(self.web_sequential_map, self.user_state)
        )
        return output + section
