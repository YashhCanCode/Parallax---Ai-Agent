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
    assert req.headers["authorization"] == "Bearer tok" and req.headers["meterless-app"] == "parallax-ai"
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


def test_validator_accepts_json_wrapped_in_a_sentence():
    raw = 'Here is the JSON: ' + _out("Profit rose 22.2% in 2024.") + ' Hope this helps.'
    out, reason = validate_narrative(raw, {"f1"}, EVIDENCE)
    assert out is not None, reason


@respx.mock
def test_narrator_uses_meterless_nightshift_and_validates_output(tmp_path):
    """Nightshift is the primary provider: auto-detected on its default port, token from the state dir."""
    import dataclasses

    from app.agents.narrator import Narrator
    from app.config import Settings
    from app.models.schemas import Classification, Finding, FindingStatus

    token = tmp_path / "proxy-token"
    token.write_text("rt-test-token")
    f = Finding(id="f1", category="risk", title="Profit rose +22.2% while operating cash flow fell -30.8% in 2024",
                claim="x", classification=Classification.interpretation, status=FindingStatus.supported, severity="elevated")
    respx.get("http://127.0.0.1:8088/v1/models").mock(return_value=httpx.Response(200, json={"data": [{"id": "meterless/auto"}]}))
    chat = respx.post("http://127.0.0.1:8088/v1/chat/completions").mock(return_value=httpx.Response(200, json={
        "model": "meterless/auto", "usage": {"total_tokens": 99},
        "choices": [{"message": {"content": _out("Profit rose 22.2% while cash flow fell 30.8% in 2024.")}}]}))
    s = dataclasses.replace(Settings(), llm_provider="auto", meterless_token_file=str(token))
    n = Narrator(s)
    assert asyncio.run(n.select_provider())[0] == "meterless"
    summary, call = asyncio.run(n.narrate("q", "Co", [f]))
    assert summary.generated_by == "meterless:meterless/auto" and call.output_accepted
    assert call.usage == {"total_tokens": 99}
    assert chat.calls[0].request.headers["authorization"] == "Bearer rt-test-token"


def test_without_nightshift_answers_are_written_in_code():
    import dataclasses

    from app.agents.narrator import Narrator
    from app.config import Settings

    n = Narrator(dataclasses.replace(Settings(), llm_provider="none"))
    assert asyncio.run(n.select_provider())[0] is None
    summary, call = asyncio.run(n.narrate("Should I buy it?", "Co", []))
    assert call is None and summary.generated_by == "deterministic"
    assert summary.answer.startswith("Parallax doesn't make investment decisions")


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


@respx.mock
def test_sample_demo_reset_starts_a_fresh_memory_round_for_fictional_companies_only():
    from app.db import set_state
    from app.integrations.meterless.hmem import HmemClient, memory_subject

    set_state("sample_demo_round", "0")
    assert memory_subject("NWM") == "NWM" and memory_subject("AAPL") == "AAPL"
    set_state("sample_demo_round", "2")
    assert memory_subject("nwm") == "NWM-R2"
    assert memory_subject("AAPL") == "AAPL"  # real companies never move
    sent = []

    def facts(request):
        body = json.loads(request.content)
        sent.append(body)
        return httpx.Response(200, json={"results": [{"key": f["key"], "outcome": "new"} for f in body["facts"]]})

    respx.post("http://hmem.test/facts").mock(side_effect=facts)
    res = asyncio.run(HmemClient("http://hmem.test").write_facts("NWM", [{"key": "NWM:revenue:2024", "value": 1.0}]))
    assert sent[0]["ticker"] == "NWM-R2" and sent[0]["facts"][0]["key"] == "NWM-R2:revenue:2024"
    assert res["results"][0]["key"] == "NWM:revenue:2024"  # callers still see their own keys
    set_state("sample_demo_round", "0")


def test_nightshift_mac_app_token_is_found_without_configuration(tmp_path):
    from app.integrations.meterless.runtime import discover_token_file

    assert discover_token_file(tmp_path) is None
    state = tmp_path / "Library" / "Application Support" / "ai.meterless.nightshift.m1m4"
    state.mkdir(parents=True)
    (state / "runtime-token").write_text("t")  # the Mac app's name; the contract's proxy-token also works
    assert discover_token_file(tmp_path) == state / "runtime-token"


@respx.mock
def test_nemotron_through_nightshift_runs_without_reasoning_and_falls_back_if_rejected():
    model = "nvidia/nemotron-3.5-lightning-30b-a3b"
    ok = httpx.Response(200, json={"model": model, "usage": {"total_tokens": 30},
                                   "choices": [{"message": {"content": "<think>x</think>{\"ok\": true}"}}]})
    route = respx.post("http://127.0.0.1:8088/v1/chat/completions").mock(side_effect=[ok])
    text, _, got, _ = asyncio.run(MeterlessRuntime("", "t", model).chat("s", "u"))
    assert json.loads(route.calls[0].request.content)["chat_template_kwargs"] == {"enable_thinking": False}
    assert text == '{"ok": true}' and got == model  # reasoning text is never shown; the reply names the model
    route = respx.post("http://127.0.0.1:8088/v1/chat/completions").mock(side_effect=[httpx.Response(400), ok])
    asyncio.run(MeterlessRuntime("", "t", model).chat("s", "u"))
    assert "chat_template_kwargs" not in json.loads(route.calls[-1].request.content)  # the retry
