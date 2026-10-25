import asyncio
import json

import httpx
import respx

from app.integrations.meterless.runtime import MeterlessRuntime, normalize_base_url, resolve_token
from app.verification.model_output import validate_narrative


def test_url_normalisation_contract():
    for raw in ["127.0.0.1:8088", "http://127.0.0.1:8088/", "http://127.0.0.1:8088/v1",
                "http://127.0.0.1:8088/v1/chat/completions", "http://127.0.0.1:8088/v1/models",
                "http://127.0.0.1:8088/healthz"]:
        assert normalize_base_url(raw) == "http://127.0.0.1:8088/v1", raw


def test_placeholder_token_rejected(tmp_path):
    assert resolve_token("rt-local", "") == ""
    f = tmp_path / "proxy-token"
    f.write_text("real-token\n")
    assert resolve_token("", str(f)) == "real-token"


@respx.mock
def test_status_states_and_headers():
    url = "http://127.0.0.1:8088/v1/models"
    route = respx.get(url).mock(return_value=httpx.Response(200, json={"data": [{"id": "meterless/auto"}]}))
    st = asyncio.run(MeterlessRuntime("127.0.0.1:8088", "tok").status())
    assert st.state == "online" and st.models == ["meterless/auto"]
    req = route.calls[0].request
    assert req.headers["authorization"] == "Bearer tok" and req.headers["meterless-app"] == "finsight-ai"
    respx.get(url).mock(return_value=httpx.Response(401))
    assert asyncio.run(MeterlessRuntime("127.0.0.1:8088", "bad").status()).state == "unauthorized"
    respx.get(url).mock(return_value=httpx.Response(200, json={"data": [{"id": "gpt-x"}]}))
    assert asyncio.run(MeterlessRuntime("127.0.0.1:8088", "t").status()).state == "offline"


@respx.mock
def test_chat_sends_scope_and_returns_usage_verbatim():
    route = respx.post("http://127.0.0.1:8088/v1/chat/completions").mock(return_value=httpx.Response(200, json={
        "model": "meterless/auto", "choices": [{"message": {"content": "{}"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2}}))
    text, usage, model, _ = asyncio.run(MeterlessRuntime("127.0.0.1:8088", "tok").chat("s", "u"))
    assert text == "{}" and usage == {"prompt_tokens": 10, "completion_tokens": 2} and model == "meterless/auto"
    assert route.calls[0].request.headers["meterless-scope"] == "user"
    assert json.loads(route.calls[0].request.content)["model"] == "meterless/auto"


EVIDENCE = 'Profit rose +22.2% while operating cash flow fell -30.8% in 2024 ... $52.40B'


def _out(summary, ids=("f1",)):
    return json.dumps({"summary": summary, "key_points": [{"text": "Cash lagged profit.", "finding_ids": list(ids)}]})


def test_validator_accepts_grounded_output():
    out, reason = validate_narrative(_out("Profit rose 22.2% in 2024 while cash flow fell 30.8%."), {"f1"}, EVIDENCE)
    assert out is not None and reason is None


def test_validator_rejects_invented_numbers_unknown_ids_advice_and_bad_json():
    assert validate_narrative(_out("Revenue will reach $80B."), {"f1"}, EVIDENCE)[1].startswith("introduced numbers")
    assert "unknown finding" in validate_narrative(_out("Fine.", ids=("zz",)), {"f1"}, EVIDENCE)[1]
    assert "recommendation" in validate_narrative(_out("You should buy the stock."), {"f1"}, EVIDENCE)[1]
    assert "valid JSON" in validate_narrative("not json", {"f1"}, EVIDENCE)[1]


NV = "https://integrate.api.nvidia.com/v1"


@respx.mock
def test_nvidia_chat_sends_bearer_disables_thinking_and_strips_think_blocks():
    from app.integrations.nvidia import DEFAULT_MODEL, NvidiaClient

    route = respx.post(f"{NV}/chat/completions").mock(return_value=httpx.Response(200, json={
        "model": DEFAULT_MODEL, "usage": {"prompt_tokens": 50, "completion_tokens": 9},
        "choices": [{"message": {"content": "<think>scratch</think>{\"summary\": \"ok\", \"key_points\": []}"}}]}))
    text, usage, model, _ = asyncio.run(NvidiaClient("nvapi-test").chat("s", "u"))
    assert text == '{"summary": "ok", "key_points": []}' and usage["completion_tokens"] == 9
    req = route.calls[0].request
    body = json.loads(req.content)
    assert req.headers["authorization"] == "Bearer nvapi-test"
    assert body["model"] == DEFAULT_MODEL == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert body["chat_template_kwargs"] == {"enable_thinking": False}


@respx.mock
def test_nvidia_retries_without_reasoning_switch_if_rejected_and_reports_bad_key():
    from app.integrations.nvidia import NvidiaClient, NvidiaError

    route = respx.post(f"{NV}/chat/completions").mock(side_effect=[
        httpx.Response(400, json={"detail": "unknown field chat_template_kwargs"}),
        httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})])
    assert asyncio.run(NvidiaClient("k").chat("s", "u"))[0] == "{}"
    assert "chat_template_kwargs" not in json.loads(route.calls[1].request.content)
    respx.post(f"{NV}/chat/completions").mock(return_value=httpx.Response(403, json={"detail": "Authorization failed"}))
    import pytest
    with pytest.raises(NvidiaError, match="rejected the key"):
        asyncio.run(NvidiaClient("bad").chat("s", "u"))


def test_validator_accepts_json_wrapped_in_a_sentence():
    raw = 'Here is the JSON: ' + _out("Profit rose 22.2% in 2024.") + ' Hope this helps.'
    out, reason = validate_narrative(raw, {"f1"}, EVIDENCE)
    assert out is not None, reason


@respx.mock
def test_narrator_uses_nemotron_when_key_set_and_validates_output():
    import dataclasses

    from app.agents.narrator import Narrator
    from app.config import Settings
    from app.models.schemas import Classification, Finding, FindingStatus

    f = Finding(id="f1", category="risk", title="Profit rose +22.2% while operating cash flow fell -30.8% in 2024",
                claim="x", classification=Classification.interpretation, status=FindingStatus.supported, severity="elevated")
    respx.post(f"{NV}/chat/completions").mock(return_value=httpx.Response(200, json={
        "model": "nvidia/nemotron-3.5-lightning-30b-a3b", "usage": {"total_tokens": 99},
        "choices": [{"message": {"content": _out("Profit rose 22.2% while cash flow fell 30.8% in 2024.")}}]}))
    s = dataclasses.replace(Settings(), llm_provider="nvidia", nvidia_api_key="nvapi-test")
    n = Narrator(s)
    assert asyncio.run(n.select_provider())[0] == "nvidia"
    summary, call = asyncio.run(n.narrate("q", "Co", [f]))
    assert summary.generated_by == "nvidia:nvidia/nemotron-3.5-lightning-30b-a3b" and call.output_accepted
    assert call.usage == {"total_tokens": 99}


@respx.mock
def test_nvidia_sends_json_schema_and_drops_it_if_rejected():
    from app.agents.narrator import NARRATIVE_SCHEMA
    from app.integrations.nvidia import NvidiaClient

    route = respx.post(f"{NV}/chat/completions").mock(side_effect=[
        httpx.Response(400, json={"detail": "response_format not supported"}),
        httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})])
    asyncio.run(NvidiaClient("k").chat("s", "u", json_schema=NARRATIVE_SCHEMA))
    first, second = (json.loads(c.request.content) for c in route.calls)
    assert first["response_format"]["type"] == "json_schema"
    assert first["response_format"]["json_schema"]["schema"]["required"] == ["answer", "summary", "key_points"]
    assert "response_format" not in second


def test_validator_rejects_number_words_the_evidence_does_not_support():
    ev = "Profit rose +22.2% while operating cash flow fell -30.8% in 2024 (3 years running)."
    bad = json.dumps({"summary": "Cash conversion has declined for four consecutive years.",
                      "key_points": [{"text": "x", "finding_ids": ["f1"]}]})
    assert "number words" in validate_narrative(bad, {"f1"}, ev)[1]
    ok = json.dumps({"summary": "Cash flow has lagged profit for three years running.",
                     "key_points": [{"text": "x", "finding_ids": ["f1"]}]})
    assert validate_narrative(ok, {"f1"}, ev)[0] is not None  # "three" matches the digit 3 in the evidence


def test_trailing_zero_numbers_count_as_the_same_number():
    from app.verification.model_output import grounded

    assert grounded("1.0", {"1"}) and grounded("2.50", {"2.5"}) and not grounded("1.5", {"1"})
