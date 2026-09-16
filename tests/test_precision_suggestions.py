from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.llm.mock import MockLLMClient
from prompt_piper_api.services.precision_suggestion_service import (
    PrecisionSuggestionService,
    PrecisionSuggestionSource,
)
from prompt_piper_api.services.semantic_precision import SemanticPrecisionEvaluator


def make_service(*, llm=None, llm_factory=None, candidates=()):
    return PrecisionSuggestionService(
        llm,
        llm_factory=llm_factory,
        lexicon=Mock(wordnet_available=True, suggest=Mock(return_value=list(candidates))),
        vector=Mock(available=False, suggest_candidates=Mock(return_value=[])),
    )


@pytest.mark.parametrize("candidates", [[], ["measurable", "specific", "concrete"]])
def test_full_prompt_reaches_model_for_generation_and_ranking(candidates):
    body = "Write a good summary.\n" + "Supporting context.\n" * 200
    body += "Final constraint: measure weekly deployment failures only."
    finding = SemanticPrecisionEvaluator().evaluate(body).findings[0]
    llm = MockLLMClient(
        chat_responder=lambda _: json.dumps({"suggested_replacements": ["measurable"]}),
    )
    result = make_service(llm=llm, candidates=candidates).suggest(
        finding=finding, body=body, card=RequirementCard(),
    )
    assert result.source == PrecisionSuggestionSource.LLM
    payload = json.loads(llm.chat_calls[0][-1].content)
    assert payload["full_prompt"] == body
    assert llm.last_chat_max_tokens is None


def test_current_model_is_resolved_again_and_cpu_mode_skips_model():
    stale = MockLLMClient()
    current = MockLLMClient(
        chat_responder=lambda _: json.dumps({"suggested_replacements": ["measurable"]}),
    )
    factory = Mock(return_value=current)
    service = make_service(llm=stale, llm_factory=factory, candidates=["measurable"])
    body = "Write a good summary."
    args = dict(
        finding=SemanticPrecisionEvaluator().evaluate(body).findings[0],
        body=body,
        card=RequirementCard(),
    )
    assert service.suggest(**args).source == PrecisionSuggestionSource.LLM
    assert len(current.chat_calls) == 1
    assert not stale.chat_calls

    factory.reset_mock()
    assert service.suggest(**args, use_llm=False).source == PrecisionSuggestionSource.WORDNET
    factory.assert_not_called()
    assert len(current.chat_calls) == 1

    # A settings change takes effect without reconstructing the service.
    factory.return_value = None
    assert not service.model_available()
    assert service.suggest(**args).source == PrecisionSuggestionSource.WORDNET

    factory.side_effect = RuntimeError("Invalid model configuration")
    assert service.suggest(**args).source == PrecisionSuggestionSource.WORDNET


def test_unhealthy_model_retains_cpu_fallback():
    service = make_service(llm=MockLLMClient(healthy=False), candidates=["measurable"])
    body = "Write a good summary."
    result = service.suggest(
        finding=SemanticPrecisionEvaluator().evaluate(body).findings[0],
        body=body,
        card=RequirementCard(),
    )
    assert result.source == PrecisionSuggestionSource.WORDNET
    assert result.suggested_replacements == ["measurable"]


def test_precision_route_forwards_cpu_selection():
    from uuid import uuid4

    from prompt_piper_api.routes.sessions import suggest_precision_replacement
    from prompt_piper_api.schemas.precision import PrecisionSuggestRequest
    from prompt_piper_api.services.precision_suggestion_service import PrecisionSuggestions

    service = Mock()
    service.suggest_precision_replacement.return_value = PrecisionSuggestions(finding_id="f1")
    session_id = uuid4()
    suggest_precision_replacement(
        session_id, PrecisionSuggestRequest(finding_id="f1", use_llm=False), service,
    )
    service.suggest_precision_replacement.assert_called_once_with(
        session_id, finding_id="f1", use_llm=False,
    )
