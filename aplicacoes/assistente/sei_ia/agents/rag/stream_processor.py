"""Processador de stream para substituir tags de citação em tempo real."""

import logging
import re

from sei_ia.agents.rag.sources import (
    create_chunk_tooltip,
    create_doc_tooltip,
    find_chunk_metadata,
    get_document_count,
)
from sei_ia.configs.logging_config import setup_logging
from sei_ia.data.pydantic_models import UserState

setup_logging()
logger = logging.getLogger(__name__)


class StreamTagProcessor:
    """Processa tags de citação durante o streaming token-by-token."""

    # Padrões para detectar início e fim de tags
    TAG_START_PATTERN = r"<(doc_\d+(?:_\d+)?)"
    TAG_END_PATTERN = r"</doc_(\d+(?:_\d+)?)>"
    COMPLETE_CHUNK_TAG = r"<doc_(\d+)_(\d+)></doc_\1_\2>"
    COMPLETE_DOC_TAG = r"<doc_(\d+)></doc_\1>"

    def __init__(self, user_state: UserState):
        """Inicializa o processador com o estado do usuário.

        Args:
            user_state: Estado com metadados dos chunks e documentos
        """
        self.user_state = user_state
        self.buffer = ""
        self.tag_buffer = ""
        self.inside_tag = False
        self.tag_start_pos = -1
        self.doc_index_map = {}  # Mapa doc_id -> índice relativo
        self.unique_doc_ids = []
        self.doc_count = get_document_count(user_state)

    def process_token(self, token: str) -> str:
        """Processa um token do stream.

        Args:
            token: Token recebido do stream

        Returns:
            String a ser impressa (vazia se acumulando tag, processada se tag completa)
        """
        # Adiciona token ao buffer principal
        self.buffer += token

        # Se estamos dentro de uma tag, acumula no tag_buffer
        if self.inside_tag:
            self.tag_buffer += token

            # Verifica se a tag foi fechada
            if self._is_tag_complete():
                # Processa a tag completa
                replacement = self._process_complete_tag()

                # Reset do estado da tag
                self.inside_tag = False
                self.tag_buffer = ""
                self.tag_start_pos = -1

                return replacement
            else:
                # Ainda acumulando a tag, não imprime nada
                return ""
        else:
            # Verifica se é início de uma tag
            if self._is_tag_start(token):
                self.inside_tag = True
                self.tag_buffer = token
                self.tag_start_pos = len(self.buffer) - len(token)
                return ""
            else:
                # Token normal, imprime diretamente
                return token

    def _is_tag_start(self, token: str) -> bool:
        """Verifica se o token marca o início de uma tag.

        Args:
            token: Token a verificar

        Returns:
            True se for início de tag
        """
        # Constrói string dos últimos caracteres incluindo o token atual
        recent_text = self.buffer[-20:] if len(self.buffer) > 20 else self.buffer

        # Verifica se começou uma tag <doc_
        if "<doc_" in recent_text:
            # Encontra a posição do início da tag
            tag_pos = recent_text.rfind("<doc_")
            # Se a tag começou recentemente (nos últimos caracteres)
            if tag_pos >= len(recent_text) - len("<doc_"):
                return True

        # Verifica padrões parciais que indicam início de tag
        return (
            recent_text.endswith("<")
            or recent_text.endswith("<d")
            or recent_text.endswith("<do")
            or recent_text.endswith("<doc")
        )

    def _is_tag_complete(self) -> bool:
        """Verifica se a tag acumulada está completa.

        Returns:
            True se a tag estiver completa
        """
        # Verifica se temos uma tag de chunk completa
        if re.match(r"^<doc_\d+_\d+></doc_\d+_\d+>$", self.tag_buffer):
            return True

        # Verifica se temos uma tag de documento completa
        return bool(re.match(r"^<doc_\d+></doc_\d+>$", self.tag_buffer))

    def _process_complete_tag(self) -> str:
        """Processa uma tag completa e retorna o HTML de substituição.

        Returns:
            HTML do tooltip ou string vazia
        """
        tag = self.tag_buffer

        # Verifica se é tag de chunk
        chunk_match = re.match(r"^<doc_(\d+)_(\d+)></doc_\1_\2>$", tag)
        if chunk_match:
            doc_id = chunk_match.group(1)
            chunk_index = chunk_match.group(2)

            logger.debug(f"Processando tag de chunk: doc={doc_id}, chunk={chunk_index}")

            # Busca metadados e cria tooltip
            chunk_metadata = find_chunk_metadata(chunk_index, doc_id, self.user_state)
            tooltip = create_chunk_tooltip(chunk_metadata)

            return tooltip

        # Verifica se é tag de documento
        doc_match = re.match(r"^<doc_(\d+)></doc_\1>$", tag)
        if doc_match:
            doc_id = doc_match.group(1)

            logger.debug(f"Processando tag de documento: doc={doc_id}")

            # Rastreia documentos únicos para índice relativo
            if doc_id not in self.doc_index_map:
                self.unique_doc_ids.append(doc_id)
                self.doc_index_map[doc_id] = len(self.unique_doc_ids)

            relative_index = self.doc_index_map[doc_id]

            # Cria tooltip (ou retorna vazio se documento único)
            tooltip = create_doc_tooltip(doc_id, relative_index, self.doc_count)

            return tooltip

        # Se não reconheceu o padrão, retorna a tag original
        logger.warning(f"Tag não reconhecida: {tag}")
        return tag

    def flush(self) -> str:
        """Retorna qualquer conteúdo pendente no buffer.

        Returns:
            Conteúdo pendente ou tag incompleta
        """
        if self.inside_tag and self.tag_buffer:
            # Se tinha uma tag incompleta, retorna ela como está
            logger.warning(f"Tag incompleta ao finalizar stream: {self.tag_buffer}")
            return self.tag_buffer
        return ""


def process_stream_with_tags(token: str, processor: StreamTagProcessor) -> str:
    """Função auxiliar para processar tokens do stream.

    Args:
        token: Token do stream
        processor: Instância do processador

    Returns:
        String processada para imprimir
    """
    return processor.process_token(token)
