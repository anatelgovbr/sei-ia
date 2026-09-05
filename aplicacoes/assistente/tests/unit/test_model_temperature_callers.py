"""Regressoes para parametros aceitos apenas pelo valor padrao do provedor."""

from unittest.mock import MagicMock, patch


def test_disclaimer_classifier_omite_temperature():
    from sei_ia.agents.disclaimer.disclaimer_classifier import classify_disclaimer_need

    llm = MagicMock()
    llm.invoke.return_value.content = '{"caso": "outro"}'
    with patch(
        "sei_ia.agents.disclaimer.disclaimer_classifier.get_llm_model",
        return_value=llm,
    ) as get_model:
        classify_disclaimer_need({"agent_tag": "principal", "user_request": "Olá"})

    assert "temperature" not in get_model.call_args.kwargs


def test_intent_selector_omite_temperature():
    from sei_ia.agents.intent_selector_agent import intent_selector_agent

    llm = MagicMock()
    llm.invoke.return_value.content = '{"intencao": "conversar"}'
    with (
        patch(
            "sei_ia.agents.intent_selector_agent.get_llm_model",
            return_value=llm,
        ) as get_model,
        patch(
            "sei_ia.agents.intent_selector_agent.check_length_context",
            return_value=True,
        ),
    ):
        intent_selector_agent({"agent_tag": "principal", "user_request": "Olá"})

    assert "temperature" not in get_model.call_args.kwargs


def test_question_generator_omite_temperature():
    from sei_ia.agents.pergunta.question_generator import generate_multiple_questions

    llm = MagicMock()
    llm.invoke.return_value.content = "Pergunta complementar"
    with patch(
        "sei_ia.agents.pergunta.question_generator.get_llm_model",
        return_value=llm,
    ) as get_model:
        generate_multiple_questions(
            {"agent_tag": "classificador", "user_request": "Olá"}
        )

    assert "temperature" not in get_model.call_args.kwargs


def test_summarize_model_omite_temperature():
    from sei_ia.agents.summarize.summarize import select_summarize_model

    with (
        patch("sei_ia.agents.summarize.summarize.get_llm_model") as get_model,
        patch("sei_ia.agents.summarize.summarize._build_summarize_graph"),
    ):
        select_summarize_model({"general_max_ctx_len": 128_000})

    assert "temperature" not in get_model.call_args.kwargs
