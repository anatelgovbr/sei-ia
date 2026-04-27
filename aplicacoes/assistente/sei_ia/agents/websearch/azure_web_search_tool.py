import asyncio
import json
import logging
from datetime import datetime

from azure.ai.agents.models import BingGroundingTool
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from sei_ia.configs.settings_config import settings
from sei_ia.services.exceptions.http_exceptions import HTTPException503
from sei_ia.services.llm_models.get_model import get_llm_model

logger = logging.getLogger(__name__)


@tool
def bing_grounding_search(query: str, count: int = 5) -> str:
    """
    Busca informações atualizadas na web usando Bing.

    Use esta ferramenta quando precisar de:
    - Informações atuais, recentes ou em tempo real
    - Notícias, eventos ou acontecimentos recentes
    - Dados específicos, estatísticas ou números atualizados
    - Verificação de informações que podem ter mudado

    Args:
        query: Pergunta ou termo de busca. Seja específico e direto.

    Returns:
        String contendo a resposta com informações encontradas e URLs das referências.
    """

    logger.info(f"bing_grounding_search chamada - Query: {query[:100]}...")

    if not all(
        [
            settings.PROJECT_ENDPOINT and settings.PROJECT_ENDPOINT.strip(),
            settings.BING_CONNECTION_NAME and settings.BING_CONNECTION_NAME.strip(),
            settings.MODEL_DEPLOYMENT_NAME and settings.MODEL_DEPLOYMENT_NAME.strip(),
        ]
    ):
        raise HTTPException503(
            detail="Error: Serviço de busca web indisponível. Configure as variáveis de ambiente necessárias."
        )

    project_client = AIProjectClient(
        endpoint=settings.PROJECT_ENDPOINT, credential=DefaultAzureCredential()
    )

    bing_tool = BingGroundingTool(
        connection_id=settings.BING_CONNECTION_NAME, set_lang="pt-BR", count=count
    )
    model_deployment = settings.MODEL_DEPLOYMENT_NAME

    logger.debug(f"Config OK - Model: {model_deployment}")

    with project_client:
        logger.debug("Criando agent...")
        agent = project_client.agents.create_agent(
            model=model_deployment,
            name="bing-search-tool",
            instructions="""
            Você é uma ferramenta de busca web especializada.

            INSTRUÇÕES CRÍTICAS:
            - Priorize SEMPRE buscas na web em vez de conhecimento interno. A sua função é buscar na internet fontes para auxiliar a resposta da pergunta do usuário.
            - Seja preciso, detalhado e objetivo
            - Adicione ao lado da fonte o DD/MM/YYYY da publicação da fonte.
            - Se não encontrar informações relevantes, diga claramente que não foi possível encontrar informações relevantes""",
            tools=bing_tool.definitions,
        )  #  REMOVER PRIORIZE, TRAGA AS URLS
        logger.debug(f"Agent criado: {agent.id}")

        logger.debug("Criando thread...")
        thread = project_client.agents.threads.create()
        logger.debug(f"Thread criado: {thread.id}")

        logger.debug("Adicionando mensagem...")
        message = project_client.agents.messages.create(
            thread_id=thread.id,
            role="user",
            content=f"{query}\n\nIMPORTANTE: Busque na web e cite todas as URLs de referência.",
        )
        logger.debug(f"Mensagem criada: {message['id']}")

        logger.debug("Executando run...")
        run = project_client.agents.runs.create_and_process(
            thread_id=thread.id,
            agent_id=agent.id,
        )
        logger.debug(f"Run concluído: status={run.status}")

        if run.status == "failed":
            error_msg = f"ERRO: Busca falhou - {run.last_error}"
            logger.error(error_msg)
            return error_msg

        logger.debug("Coletando mensagens...")
        messages = project_client.agents.messages.list(thread_id=thread.id)

        response_text = ""
        all_references = []
        ref_counter = 1

        # Capturar as mensagens que o agente de busca da Azure AI Project retornou
        for msg in messages:
            if msg.role == "assistant":
                logger.debug("Mensagem assistant encontrada")
                if hasattr(msg.content, "__iter__") and not isinstance(
                    msg.content, str
                ):
                    for idx, content_item in enumerate(msg.content):
                        if hasattr(content_item, "text"):
                            text_value = content_item.text.value
                            logger.debug(f"Text block {idx}: {len(text_value)} chars")

                            if hasattr(content_item.text, "annotations"):
                                annotations = content_item.text.annotations
                                # Ordenar por start_index decrescente para não deslocar índices
                                sorted_annots = sorted(
                                    [
                                        a
                                        for a in annotations
                                        if hasattr(a, "url_citation") and a.url_citation
                                    ],
                                    key=lambda a: a.start_index,
                                    reverse=True,
                                )

                                for annotation in sorted_annots:
                                    # Substituir marcador 【...】 por <web_N></web_N>
                                    marker = f"<web_{ref_counter}></web_{ref_counter}>"
                                    text_value = (
                                        text_value[: annotation.start_index]
                                        + marker
                                        + text_value[annotation.end_index :]
                                    )

                                    all_references.append(
                                        {
                                            "idx": ref_counter,
                                            "url": annotation.url_citation.url,
                                            "title": getattr(
                                                annotation.url_citation, "title", ""
                                            )
                                            or "",
                                        }
                                    )
                                    ref_counter += 1

                            response_text += text_value
                else:
                    response_text = str(msg.content)
                    logger.debug(f"Content direto (string): {len(response_text)} chars")

    result = json.dumps(
        {"text": response_text, "references": all_references}, ensure_ascii=False
    )
    logger.info(
        f"bing_grounding_search concluída - Retornando JSON com {len(all_references)} referências"
    )

    return result


@tool
def bing_grounding_search_1_results(query: str) -> str:
    """
    Busca informações atualizadas na web usando Bing com 1 resultado.

    Use esta ferramenta quando precisar de:
    - Informações atuais, recentes ou em tempo real
    - Notícias, eventos ou acontecimentos recentes
    - Dados específicos, estatísticas ou números atualizados
    - Verificação de informações que podem ter mudado

    Args:
        query: Pergunta ou termo de busca. Seja específico e direto.

    Returns:
        String contendo a resposta com informações encontradas e URLs das referências.
    """
    logger.info(f"bing_grounding_search_1_results chamada - Query: {query[:100]}...")

    # Validação de configuração
    if not all(
        [
            settings.PROJECT_ENDPOINT and settings.PROJECT_ENDPOINT.strip(),
            settings.BING_CONNECTION_NAME and settings.BING_CONNECTION_NAME.strip(),
            settings.MODEL_DEPLOYMENT_NAME and settings.MODEL_DEPLOYMENT_NAME.strip(),
        ]
    ):
        raise HTTPException503(
            detail="Error: Serviço de busca web indisponível. Configure as variáveis de ambiente necessárias."
        )

    # Chamada direta ao Azure AI Project Client (SEM agente ReACT aninhado)
    project_client = AIProjectClient(
        endpoint=settings.PROJECT_ENDPOINT, credential=DefaultAzureCredential()
    )

    bing_tool = BingGroundingTool(
        connection_id=settings.BING_CONNECTION_NAME, set_lang="pt-BR", count=1
    )
    model_deployment = settings.MODEL_DEPLOYMENT_NAME

    logger.debug(f"Config OK - Model: {model_deployment}")

    with project_client:
        logger.debug("Criando agent...")
        agent = project_client.agents.create_agent(
            model=model_deployment,
            name="bing-search-tool",
            instructions="""
            Você é uma ferramenta de busca web especializada.

            INSTRUÇÕES CRÍTICAS:
            - Priorize SEMPRE buscas na web em vez de conhecimento interno
            - Seja preciso, detalhado e objetivo
            - Cite URLs específicas de onde tirou cada informação
            - Se não encontrar informações, diga claramente""",
            tools=bing_tool.definitions,
        )
        logger.debug(f"Agent criado: {agent.id}")

        logger.debug("Criando thread...")
        thread = project_client.agents.threads.create()
        logger.debug(f"Thread criado: {thread.id}")

        logger.debug("Adicionando mensagem...")
        message = project_client.agents.messages.create(
            thread_id=thread.id,
            role="user",
            content=f"{query}\n\nIMPORTANTE: Busque na web e cite todas as URLs de referência.",
        )
        logger.debug(f"Mensagem criada: {message['id']}")

        logger.debug("Executando run...")
        run = project_client.agents.runs.create_and_process(
            thread_id=thread.id,
            agent_id=agent.id,
        )
        logger.debug(f"Run concluído: status={run.status}")

        if run.status == "failed":
            error_msg = f"ERRO: Busca falhou - {run.last_error}"
            logger.error(error_msg)
            return error_msg

        logger.debug("Coletando mensagens...")
        messages = project_client.agents.messages.list(thread_id=thread.id)

        response_text = ""
        all_references = []
        ref_counter = 1

        for msg in messages:
            if msg.role == "assistant":
                logger.debug("Mensagem assistant encontrada")
                if hasattr(msg.content, "__iter__") and not isinstance(
                    msg.content, str
                ):
                    for idx, content_item in enumerate(msg.content):
                        if hasattr(content_item, "text"):
                            text_value = content_item.text.value
                            logger.debug(f"Text block {idx}: {len(text_value)} chars")

                            # Processar annotations se existirem
                            if hasattr(content_item.text, "annotations"):
                                annotations = content_item.text.annotations
                                # Ordenar por start_index decrescente para não deslocar índices
                                sorted_annots = sorted(
                                    [
                                        a
                                        for a in annotations
                                        if hasattr(a, "url_citation") and a.url_citation
                                    ],
                                    key=lambda a: a.start_index,
                                    reverse=True,
                                )

                                for annotation in sorted_annots:
                                    # Substituir marcador 【...】 por <web_N></web_N>
                                    marker = f"<web_{ref_counter}></web_{ref_counter}>"
                                    text_value = (
                                        text_value[: annotation.start_index]
                                        + marker
                                        + text_value[annotation.end_index :]
                                    )

                                    all_references.append(
                                        {
                                            "idx": ref_counter,
                                            "url": annotation.url_citation.url,
                                            "title": getattr(
                                                annotation.url_citation, "title", ""
                                            )
                                            or "",
                                        }
                                    )
                                    ref_counter += 1

                            response_text += text_value
                else:
                    response_text = str(msg.content)
                    logger.debug(f"Content direto (string): {len(response_text)} chars")

        logger.debug(f"Resposta coletada: {len(response_text)} chars")
        logger.debug(f"Referências encontradas: {len(all_references)}")

    # Retornar JSON estruturado
    result = json.dumps(
        {"text": response_text, "references": all_references}, ensure_ascii=False
    )

    logger.info(
        f"bing_grounding_search_1_results concluída - Retornando JSON com {len(all_references)} referências"
    )

    return result


class BingGroundingAgent:
    """Agente LangGraph que usa Bing como tool"""

    def __init__(
        self,
        tools: list[BingGroundingTool] = [bing_grounding_search],  # noqa: B006
    ):
        system_message = f"""
        Você é um assistente inteligente com acesso a busca web via Bing Grounding.

        QUANDO USAR A FERRAMENTA bing_grounding_search:
        ✓ Informações atuais, recentes ou que mudam frequentemente
        ✓ Notícias, eventos ou acontecimentos recentes
        ✓ Dados específicos, estatísticas ou números atualizados
        ✓ Informações sobre pessoas, empresas ou organizações que podem ter mudado
        ✓ Qualquer pergunta que requer dados em tempo real
        ✓ Quando o usuário pede explicitamente para buscar na web

        QUANDO NÃO USAR:
        ✗ Conhecimento geral e estabelecido (conceitos, definições)
        ✗ Perguntas sobre matemática, lógica ou raciocínio
        ✗ Tópicos históricos bem estabelecidos
        ✗ Explicações de conceitos teóricos

        COMO USAR A FERRAMENTA bing_grounding_search:
        1. Identifique os termos-chave da pergunta
        2. Formule queries específicas e diretas para cada aspecto
        3. Chame bing_grounding_search MÚLTIPLAS VEZES se necessário para cobrir diferentes aspectos da pergunta
        4. Use os resultados para formular sua resposta final
        5. Utilize a DATA DE HOJE quando for necessário para o contexto da ferramenta buscar na web.

        DATA DE HOJE: {datetime.now().strftime("%d/%m/%Y")}

        REGRA CRÍTICA:
            Caso não exista a necessidade de usar a tool bing_grounding_search, você DEVE responder apenas com : "não foi necessário buscar na web."
        """
        agent_react = create_react_agent(
            model=get_llm_model(model_type=settings.WEBSEARCH_AGENT_MODEL),
            tools=tools,
            prompt=system_message,
        )
        self.agent = agent_react

    async def process_user_prompt(self, user_prompt: str):
        try:
            return await self.agent.ainvoke(
                {"messages": [HumanMessage(content=user_prompt)]}
            )
        except AttributeError as e:
            if "'str' object has no attribute 'model_dump'" in str(e):
                # Captura a resposta da API do frame onde ocorreu o erro
                response_str = None
                tb = e.__traceback__
                while tb:
                    if "response" in tb.tb_frame.f_locals:
                        response_str = tb.tb_frame.f_locals["response"]
                    tb = tb.tb_next

                error_msg = (
                    "Azure OpenAI retornou resposta inválida (string em vez de objeto estruturado). "
                    "Possível content filtering, rate limiting ou problema na API."
                )
                if response_str:
                    error_msg += f" Resposta recebida: {response_str}"

                raise ValueError(error_msg) from e
            raise


async def main():
    agent = BingGroundingAgent()

    # Teste
    prompt = """Preciso de uma análise detalhada e abrangente sobre a situação atual da ANATEL e suas principais lideranças:

PARTE 1 - HISTÓRICO E MANDATOS:
1. Quando Carlos Manuel Baigorri assumiu a presidência da ANATEL? Qual foi a data exata de início do seu mandato como presidente?
2. Qual é a duração prevista do mandato de Baigorri como presidente da ANATEL conforme a legislação brasileira?
3. Houve alguma decisão do TCU (Tribunal de Contas da União) que prorrogou ou alterou o mandato de Baigorri? Se sim, quais foram os detalhes dessa decisão e até quando vai o mandato dele agora?
4. Quando termina o mandato de Baigorri como conselheiro da ANATEL (não como presidente)? Existe diferença entre o mandato de presidente e o mandato de conselheiro?

PARTE 2 - ALEXANDRE FREIRE:
5. Quem é Alexandre Freire? Quando ele foi nomeado conselheiro da ANATEL?
6. Qual a data de início e a data de término do mandato de Alexandre Freire como conselheiro da ANATEL?
7. Alexandre Freire já ocupou ou ocupa algum cargo de liderança na ANATEL além de conselheiro?
8. Qual é o histórico profissional de Alexandre Freire antes de entrar na ANATEL?

PARTE 3 - SUCESSÃO E REGRAS:
9. Quais são as regras legais para sucessão da presidência da ANATEL? Existe algum impedimento legal para que um conselheiro assuma a presidência?
10. Alexandre Freire pode ser nomeado presidente da ANATEL quando o mandato de Baigorri terminar? Quais são os requisitos e impedimentos?
11. Se Alexandre Freire for nomeado presidente da ANATEL, até quando seria seu mandato como presidente considerando as regras atuais?
12. A extensão de mandato concedida pelo TCU a Baigorri se aplicaria automaticamente a Alexandre Freire caso ele seja nomeado presidente? Explique juridicamente.

PARTE 4 - CONTEXTO POLÍTICO ATUAL:
13. Quais foram as principais decisões e polêmicas envolvendo a ANATEL nos últimos 12 meses?
14. Como está a relação entre a ANATEL e o governo federal atual? Houve algum conflito ou tensão recente?
15. Quais são as principais operadoras de telecomunicações que a ANATEL regula e quais foram as maiores autuações ou decisões contra elas recentemente?

PARTE 5 - COMPOSIÇÃO DO CONSELHO:
16. Quem são todos os conselheiros atuais da ANATEL? Liste nome completo, data de nomeação e término de mandato de cada um.
17. Quantas vagas de conselheiro existem na ANATEL e quantas estão preenchidas atualmente?
18. Há alguma vaga vencida ou que vencerá em breve que o governo federal precisa preencher?

PARTE 6 - ANÁLISE PROSPECTIVA:
19. Baseado nas informações encontradas, qual é o cenário mais provável para a sucessão da presidência da ANATEL nos próximos 24 meses?
20. Quais são os nomes que estão sendo cotados na imprensa especializada como possíveis sucessores de Baigorri?

Para cada informação fornecida, cite a fonte e a data da publicação. Organize a resposta de forma estruturada, separando cada parte claramente."""

    logger.info(f"Pergunta: {prompt[:100]}...")

    result = await agent.process_user_prompt(prompt)

    logger.info("Resposta recebida")
    if len(result.get("messages")) > 0:
        message = result.get("messages", [])[-1].content
    else:
        message = "Nenhuma resposta encontrada"
    print(message)


if __name__ == "__main__":
    asyncio.run(main())
