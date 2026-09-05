"""Testes unitários para os módulos de prompts em sei_ia/agents/prompts/."""

from sei_ia.agents.prompts.completation import (
    COMPLETATION_WITH_DOC,
    COMPLETATION_WITH_DOC_INSTRUCTION,
    INTERMEDIATE_COMPLETATION_WITH_DOC,
    INTERMEDIATE_COMPLETATION_WITH_DOC_FOR_FALSE_RAG,
)
from sei_ia.agents.prompts.disclaimer_need_identifier import (
    DICT_DISCLAIMER_CASES,
    PONDER_DISCLAIMER_ADDITION_PROMPT,
)
from sei_ia.agents.prompts.intent_selector import (
    DICT_DOCUMENTS_INTENTIONS,
    INTENT_DOCUMENTS_SELECTION_PROMPT,
)
from sei_ia.agents.prompts.memory import SYSTEM_PROMPT_WITH_MEMORY
from sei_ia.agents.prompts.question_generation import GENERATE_QUESTIONS_PROMPT
from sei_ia.agents.prompts.rag import (
    DOC_METADATA_CHUNKS,
    INSTRUCTIONS_SOURCES,
    PROMPT_RAG,
)
from sei_ia.agents.prompts.summarization import (
    COMBINE_PROMPT,
    PROMPT_ONE_CHUNK,
    PROMPT_REFINED,
)
from sei_ia.agents.prompts.system import (
    SYSTEM_MESSAGE_INTENT,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_v2,
)
from sei_ia.agents.prompts.web_search import WEB_SEARCH_PROMPT


class TestCompletationPrompts:
    def test_completation_with_doc_eh_string(self):
        assert isinstance(COMPLETATION_WITH_DOC, str)

    def test_completation_with_doc_nao_vazio(self):
        assert len(COMPLETATION_WITH_DOC) > 0

    def test_completation_with_doc_tem_placeholder_text(self):
        assert "{text}" in COMPLETATION_WITH_DOC

    def test_completation_with_doc_tem_placeholder_conteudo(self):
        assert "{conteudo_documentos}" in COMPLETATION_WITH_DOC

    def test_completation_with_doc_instruction_eh_string(self):
        assert isinstance(COMPLETATION_WITH_DOC_INSTRUCTION, str)

    def test_completation_with_doc_instruction_tem_placeholder_instruction(self):
        assert "{instruction}" in COMPLETATION_WITH_DOC_INSTRUCTION

    def test_completation_with_doc_instruction_tem_placeholder_text(self):
        assert "{text}" in COMPLETATION_WITH_DOC_INSTRUCTION

    def test_intermediate_completation_eh_string(self):
        assert isinstance(INTERMEDIATE_COMPLETATION_WITH_DOC, str)

    def test_intermediate_completation_tem_conteudo(self):
        assert "<conteudo>" in INTERMEDIATE_COMPLETATION_WITH_DOC
        assert "{doc}" in INTERMEDIATE_COMPLETATION_WITH_DOC

    def test_intermediate_completation_for_false_rag_eh_string(self):
        assert isinstance(INTERMEDIATE_COMPLETATION_WITH_DOC_FOR_FALSE_RAG, str)

    def test_intermediate_completation_for_false_rag_tem_metadata(self):
        assert "{metadata_proc}" in INTERMEDIATE_COMPLETATION_WITH_DOC_FOR_FALSE_RAG


class TestRagPrompts:
    def test_instructions_sources_eh_string(self):
        assert isinstance(INSTRUCTIONS_SOURCES, str)

    def test_instructions_sources_nao_vazio(self):
        assert len(INSTRUCTIONS_SOURCES) > 0

    def test_instructions_sources_menciona_source(self):
        assert "Source" in INSTRUCTIONS_SOURCES

    def test_prompt_rag_eh_string(self):
        assert isinstance(PROMPT_RAG, str)

    def test_prompt_rag_tem_placeholder_prompt(self):
        assert "{prompt}" in PROMPT_RAG

    def test_prompt_rag_tem_placeholder_emb_text(self):
        assert "{emb_text}" in PROMPT_RAG

    def test_doc_metadata_chunks_eh_string(self):
        assert isinstance(DOC_METADATA_CHUNKS, str)

    def test_doc_metadata_chunks_tem_placeholder_chunk(self):
        assert "{chunk}" in DOC_METADATA_CHUNKS


class TestSummarizationPrompts:
    def test_prompt_one_chunk_eh_string(self):
        assert isinstance(PROMPT_ONE_CHUNK, str)

    def test_prompt_one_chunk_tem_placeholder_text(self):
        assert "{text}" in PROMPT_ONE_CHUNK

    def test_combine_prompt_eh_string(self):
        assert isinstance(COMBINE_PROMPT, str)

    def test_combine_prompt_tem_placeholder_text(self):
        assert "{text}" in COMBINE_PROMPT

    def test_prompt_refined_eh_string(self):
        assert isinstance(PROMPT_REFINED, str)

    def test_prompt_refined_tem_placeholder_resumo(self):
        assert "{resumo_inicial}" in PROMPT_REFINED

    def test_prompt_refined_tem_placeholder_text(self):
        assert "{text}" in PROMPT_REFINED


class TestSystemPrompts:
    def test_system_prompt_eh_string(self):
        assert isinstance(SYSTEM_PROMPT, str)

    def test_system_prompt_nao_vazio(self):
        assert len(SYSTEM_PROMPT) > 0

    def test_system_prompt_v2_eh_string(self):
        assert isinstance(SYSTEM_PROMPT_v2, str)

    def test_system_prompt_v2_nao_vazio(self):
        assert len(SYSTEM_PROMPT_v2) > 0

    def test_system_message_intent_eh_string(self):
        assert isinstance(SYSTEM_MESSAGE_INTENT, str)

    def test_system_message_intent_nao_vazio(self):
        assert len(SYSTEM_MESSAGE_INTENT) > 0


class TestIntentSelectorPrompts:
    def test_dict_documents_intentions_eh_dict(self):
        assert isinstance(DICT_DOCUMENTS_INTENTIONS, dict)

    def test_dict_documents_intentions_tem_pergunta(self):
        assert "pergunta" in DICT_DOCUMENTS_INTENTIONS

    def test_dict_documents_intentions_tem_resumo(self):
        assert "resumo" in DICT_DOCUMENTS_INTENTIONS

    def test_dict_documents_intentions_tem_conversar(self):
        assert "conversar" in DICT_DOCUMENTS_INTENTIONS

    def test_dict_documents_intentions_tem_analise(self):
        assert "analise" in DICT_DOCUMENTS_INTENTIONS

    def test_dict_documents_intentions_todos_valores_sao_strings(self):
        for v in DICT_DOCUMENTS_INTENTIONS.values():
            assert isinstance(v, str)

    def test_intent_documents_selection_prompt_eh_string(self):
        assert isinstance(INTENT_DOCUMENTS_SELECTION_PROMPT, str)

    def test_intent_documents_selection_prompt_tem_placeholder_intentions(self):
        assert "{intentions}" in INTENT_DOCUMENTS_SELECTION_PROMPT

    def test_intent_documents_selection_prompt_tem_placeholder_prompt(self):
        assert "{prompt}" in INTENT_DOCUMENTS_SELECTION_PROMPT


class TestWebSearchPrompt:
    def test_web_search_prompt_eh_string(self):
        assert isinstance(WEB_SEARCH_PROMPT, str)

    def test_web_search_prompt_nao_vazio(self):
        assert len(WEB_SEARCH_PROMPT) > 0

    def test_web_search_prompt_menciona_busca_n(self):
        assert "busca_N" in WEB_SEARCH_PROMPT or "busca_" in WEB_SEARCH_PROMPT


class TestMemoryPrompt:
    def test_memory_prompt_eh_string(self):
        assert isinstance(SYSTEM_PROMPT_WITH_MEMORY, str)

    def test_memory_prompt_nao_vazio(self):
        assert len(SYSTEM_PROMPT_WITH_MEMORY) > 0

    def test_memory_prompt_tem_placeholder_history(self):
        assert "{history}" in SYSTEM_PROMPT_WITH_MEMORY


class TestQuestionGenerationPrompt:
    def test_question_generation_prompt_eh_string(self):
        assert isinstance(GENERATE_QUESTIONS_PROMPT, str)

    def test_question_generation_prompt_nao_vazio(self):
        assert len(GENERATE_QUESTIONS_PROMPT) > 0

    def test_question_generation_prompt_tem_placeholder_user_question(self):
        assert "{user_question}" in GENERATE_QUESTIONS_PROMPT

    def test_question_generation_prompt_tem_placeholder_n_questions(self):
        assert "{n_questions}" in GENERATE_QUESTIONS_PROMPT


class TestDisclaimerPrompts:
    def test_dict_disclaimer_cases_eh_dict(self):
        assert isinstance(DICT_DISCLAIMER_CASES, dict)

    def test_dict_disclaimer_cases_tem_outro(self):
        assert "outro" in DICT_DISCLAIMER_CASES

    def test_dict_disclaimer_cases_tem_totalidade_sei(self):
        assert "totalidade_do_sei" in DICT_DISCLAIMER_CASES

    def test_dict_disclaimer_cases_tem_orientacao_uso_sei(self):
        assert "orientacao_sobre_uso_do_sei" in DICT_DISCLAIMER_CASES

    def test_dict_disclaimer_cases_todos_valores_sao_strings(self):
        for v in DICT_DISCLAIMER_CASES.values():
            assert isinstance(v, str)

    def test_ponder_disclaimer_prompt_eh_string(self):
        assert isinstance(PONDER_DISCLAIMER_ADDITION_PROMPT, str)

    def test_ponder_disclaimer_prompt_tem_placeholder_intentions(self):
        assert "{intentions}" in PONDER_DISCLAIMER_ADDITION_PROMPT

    def test_ponder_disclaimer_prompt_tem_placeholder_prompt(self):
        assert "{prompt}" in PONDER_DISCLAIMER_ADDITION_PROMPT
