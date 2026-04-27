#!/usr/bin/env python3
# uv run stream_client.py run_test.py --verbose
"""Cliente para consumir o endpoint de streaming do assistente."""

import asyncio
import json
import time
from datetime import datetime
from typing import Any

import httpx


class StreamClient:
    """Cliente para consumir streams do endpoint /llm_lang/stream."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """Inicializa o cliente com a URL base do servidor.

        Args:
            base_url: URL base do servidor (ex: http://localhost:8000)
        """
        self.base_url = base_url.rstrip("/")
        self.endpoint = f"{self.base_url}/llm_lang/stream"

    async def stream_chat(
        self,
        payload: dict[str, Any],
        verbose: bool = False,
    ) -> None:
        """Envia mensagem e consome o stream de resposta.

        Args:
            message: Mensagem para enviar ao assistente (se não usar payload)
            user_id: ID do usuário (opcional)
            topic_id: ID do tópico (opcional)
            verbose: Exibe informações detalhadas do stream
            payload: Payload completo no formato do SEI (sobrescreve outros parâmetros)
        """
        # Usa payload se fornecido, senão cria formato simples
        request_data = payload

        try:
            async with (
                httpx.AsyncClient(timeout=300.0, verify=False) as client,
                client.stream(
                    "POST",
                    self.endpoint,
                    json=request_data,
                    headers={"Accept": "text/event-stream"},
                ) as response,
            ):
                if response.status_code != 200:
                    print(f"❌ Erro HTTP {response.status_code}: {response.text}")
                    return

                print("✅ Conexão estabelecida. Aguardando dados...\n")

                content_buffer = ""
                metadata = None

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: "

                        try:
                            data = json.loads(data_str)
                            await self._process_chunk(data, verbose)

                            # Acumula conteúdo para exibição final
                            if data.get("type") == "content":
                                content_buffer += data.get("data", "")
                            elif data.get("type") == "metadata":
                                metadata = data.get("data", {})
                            elif data.get("type") == "end":
                                break

                        except json.JSONDecodeError as e:
                            if verbose:
                                print(f"⚠️  Erro ao decodificar JSON: {e}")
                                print(f"Raw data: {data_str}")

                # Exibe resumo final
                print("\n" + "=" * 60)
                print("📊 RESUMO DA SESSÃO:")
                print(f"💬 Conteúdo recebido: {len(content_buffer)} caracteres")

                if metadata and verbose:
                    print("📈 Metadados:")
                    print(f"  - ID da resposta: {metadata.get('id_resposta', 'N/A')}")
                    print(f"  - Modelo usado: {metadata.get('model_type', 'N/A')}")
                    if "doc_rag" in metadata and metadata["doc_rag"]:
                        print(
                            f"  - Documentos RAG: {len(metadata['doc_rag'])} documentos"
                        )

        except httpx.ConnectError:
            print(
                f"❌ Erro de conexão. Verifique se o servidor está rodando em {self.base_url}"
            )
        except httpx.TimeoutException:
            print("❌ Timeout na requisição")
        except KeyboardInterrupt:
            print("\n🛑 Interrompido pelo usuário")
        except Exception as e:
            print(f"❌ Erro inesperado: {e}")

    async def _process_chunk(self, data: dict[str, Any], verbose: bool = False) -> None:
        """Processa um chunk de dados recebido.

        Args:
            data: Dados do chunk
            verbose: Exibe informações detalhadas
        """
        chunk_type = data.get("type", "unknown")
        timestamp = data.get("timestamp", time.time())
        content = data.get("data", "")

        if chunk_type == "content":
            # Exibe o conteúdo em tempo real (sem quebra de linha)
            print(content, end="", flush=True)

        elif chunk_type == "metadata":
            print("Metadados recebidos", data)
            # if verbose:
            #     print(f"\n📋 Metadados recebidos às {datetime.fromtimestamp(timestamp)}")

        elif chunk_type == "end":
            if verbose:
                print(f"\n🏁 Stream finalizado às {datetime.fromtimestamp(timestamp)}")

        elif chunk_type == "error":
            print(f"\n❌ Erro: {content}")

        elif verbose:
            print(f"\n🔍 Chunk desconhecido ({chunk_type}): {content}")


async def main():
    """Função principal do cliente."""
    client = StreamClient(base_url="https://rhgicdhmin01:8088")
    payload = {
        "id_usuario": 0,
        "id_topico": 0,
        "system_prompt": "Sou o Assistente de IA do SEI, desenvolvido para facilitar o manejo de processos no SEI (Sistema Eletrônico de Informações) da ANATEL. Estou aqui para auxiliar na instrução de processos eletrônicos, fornecendo informações confiáveis e atualizadas. Meu idioma principal é o português brasileiro, mas posso me ajustar a outros idiomas. Para elementos fictícios previsões ou suposições, respondo com 'ATENÇÃO: Esta resposta pode conter elementos fictícios, previsões ou suposições não baseadas em dados concretos.'",
        "text": "Pesquisar bastante e com cuidado na internet por Jurisprudência do Poder Judiciário Federal (TRFs e STJ) que sustente a decisão tomada no documento #14412083",
        "max_tokens": 4000,
        "temperature": 0,
        "use_websearch": False,  # True,
        "id_procedimentos": [
            {
                "id_procedimento": "10946774",
                "id_documentos": [
                    {
                        "id_documento": "16148358",
                        "download_ext": False,
                        "pag_doc_init": 0,
                        "pag_doc_end": 0,
                    }
                ],
            }
        ],
    }

    await client.stream_chat(
        payload=payload,
        verbose=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
