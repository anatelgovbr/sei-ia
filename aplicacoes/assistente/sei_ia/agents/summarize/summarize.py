"""This module implements a summarization pipeline using LangGraph for map-reduce summarization of large documents."""

from __future__ import annotations

import logging
import operator
from typing import TYPE_CHECKING, Annotated, Literal, TypedDict

from langchain.text_splitter import TokenTextSplitter
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langgraph.constants import Send
from langgraph.graph import END, START, StateGraph

from sei_ia.agents.prompts.summarization import COMBINE_PROMPT, PROMPT_ONE_CHUNK
from sei_ia.configs.logging_config import setup_logging
from sei_ia.configs.settings_config import settings
from sei_ia.services.llm_models.get_model import get_llm_model, get_summarize_model

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.runnables import Runnable

    from sei_ia.data.pydantic_models import UserState

setup_logging()
logger = logging.getLogger(__name__)


onechunk_prompt_template = PromptTemplate(
    input_variables=["text"], template=PROMPT_ONE_CHUNK
)
combine_prompt_template = PromptTemplate(
    input_variables=["text"], template=COMBINE_PROMPT
)


def split_text_summarize(doc: str) -> tuple[list[Document], str]:
    """Split a raw document string into langchain Document chunks."""
    logger.debug("split_text_summarize IN")
    params = get_summarize_model()
    splitter = TokenTextSplitter(
        encoding_name=params["token_encoding_name"],
        chunk_size=params["chunk_size"],
        chunk_overlap=25,
    )
    chunks = splitter.create_documents([doc])
    logger.debug("split_text_summarize OUT")
    return chunks, "small"


class SummaryOverallState(TypedDict):
    """Defines the overall state of the summarization process."""

    contents: list[str]  # initial input
    summaries: Annotated[list[str], operator.add]
    collapsed_summaries: Annotated[list[Document], operator.add]


class _SummaryInput(TypedDict):
    """Defines the input structure for summarization."""

    content: str


def _build_summarize_graph(llm: BaseChatModel, max_ctx_tokens: int) -> Runnable:  # noqa: C901
    """Return a compiled LangGraph Runnable that performs map-reduce summarisation."""

    def length_fn(docs: list[Document]) -> int:
        """Total #tokens over all docs using the model's tokenizer."""
        return sum(llm.get_num_tokens(d.page_content) for d in docs)

    def generate_summary(state: _SummaryInput) -> SummaryOverallState:
        """Generate a summary for the given content in the state."""
        text = state["content"]
        prompt = onechunk_prompt_template.format(text=text)
        resp = llm.predict(prompt)
        return {"summaries": [resp]}

    def map_edge(state: SummaryOverallState) -> list[Send]:
        """Map edges to generate summaries and parallelize using Send."""
        return [Send("generate_summary", {"content": c}) for c in state["contents"]]

    def collect_summaries(state: SummaryOverallState) -> SummaryOverallState:
        """Collect summaries and convert them into Document objects."""
        docs = [Document(page_content=s) for s in state["summaries"]]
        return {"collapsed_summaries": docs}

    def collapse_summaries(state: SummaryOverallState) -> SummaryOverallState:
        """Collapse summaries into partitions based on token budget."""
        current, baskets = [], []
        running_tokens = 0
        for doc in state["collapsed_summaries"]:
            t = llm.get_num_tokens(doc.page_content)
            if running_tokens + t > max_ctx_tokens:
                baskets.append(list(current))
                current, running_tokens = [], 0
            current.append(doc)
            running_tokens += t
        if current:
            baskets.append(list(current))

        results = []
        for group in baskets:
            joined_text = "\n\n".join(d.page_content for d in group)
            prompt = combine_prompt_template.format(text=joined_text)
            results.append(Document(page_content=llm.predict(prompt)))
        return {"collapsed_summaries": results}

    def need_collapse(
        state: SummaryOverallState,
    ) -> Literal["collapse_summaries", "__end__"]:
        if length_fn(state["collapsed_summaries"]) > max_ctx_tokens:
            return "collapse_summaries"
        return "__end__"

    graph = StateGraph(SummaryOverallState)
    graph.add_node("generate_summary", generate_summary)
    graph.add_node("collect_summaries", collect_summaries)
    graph.add_node("collapse_summaries", collapse_summaries)

    graph.add_conditional_edges(START, map_edge, ["generate_summary"])
    graph.add_edge("generate_summary", "collect_summaries")
    graph.add_conditional_edges("collect_summaries", need_collapse)
    graph.add_conditional_edges(
        "collapse_summaries",
        need_collapse,
        {"__end__": END, "collapse_summaries": "collapse_summaries"},
    )

    return graph.compile()


def select_summarize_model(user_state: UserState) -> Runnable:
    """Return a LangGraph Runnable (compiled) that executes map-reduce summarisation."""
    logger.debug("select_summarize_model IN")

    llm = get_llm_model(
        settings.SUMMARIZE_MODEL,
        temperature=settings.SUMMARIZE_TEMPERATURE,
        max_tokens=settings.SUMMARIZE_CHUNK_MAX_OUTPUT,
    )

    runnable = _build_summarize_graph(
        llm, max_ctx_tokens=user_state["general_max_ctx_len"]
    )
    logger.debug("select_summarize_model OUT")
    return runnable
