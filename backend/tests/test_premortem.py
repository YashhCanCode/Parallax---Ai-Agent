import json

from app.decisions import premortem as pm
from app.reconciliation.engine import revision_findings
from app.risk_analysis.indicators import run_risk_indicators


def _findings(obs):
    return run_risk_indicators(obs) + revision_findings(obs, "revenue")


def test_deterministic_voices_cite_real_findings(nwm):
    fs = _findings(nwm.observations)
    out = pm.deterministic(fs)
    ids = {f.id for f in fs}
    assert 1 <= len(out["skeptic"]) <= 4 and 1 <= len(out["defender"]) <= 4
    assert out["skeptic"][0]["text"].startswith("Profit rose")  # the elevated warning comes first
    assert any("Counterevidence" in p["text"] for p in out["defender"])
    assert all(i in ids for side in out.values() for p in side for i in p["finding_ids"])


def test_questions_include_personal_and_finding_specific(nwm):
    qs = pm.questions(_findings(nwm.observations))
    texts = " ".join(q["question"] for q in qs)
    assert "fell by 40%" in texts and "within the next 3 years" in texts
    assert "why profit isn't turning into cash" in texts and "debt paying for" in texts and "original or revised" in texts


def test_validator_accepts_grounded_and_rejects_bad_voices(nwm):
    ev = pm.evidence_for(_findings(nwm.observations))
    cash = next(e for e in ev if e["id"].startswith("risk-cash"))
    good = {"skeptic": [{"text": "Profit rose 22.2% while operating cash flow fell 30.8%.", "finding_ids": [cash["id"]]}],
            "defender": [{"text": "Operating cash flow is still positive.", "finding_ids": [cash["id"]]}]}
    assert pm.validate(json.dumps(good), ev)[0] is not None
    bad_num = {**good, "skeptic": [{"text": "Revenue could reach $777B.", "finding_ids": [cash["id"]]}]}
    assert "introduced numbers" in pm.validate(json.dumps(bad_num), ev)[1]
    predict = {**good, "skeptic": [{"text": "Revenue will drop next year.", "finding_ids": [cash["id"]]}]}
    assert "advice or a verdict" in pm.validate(json.dumps(predict), ev)[1]
    rev = next(e for e in ev if e["id"].startswith("rev-"))
    asserted = {**good, "defender": [{"text": "The restatement is a routine adjustment.", "finding_ids": [rev["id"]]}]}
    assert "asserted a cause" in pm.validate(json.dumps(asserted), ev)[1]
    hedged = {**good, "defender": [{"text": "The restatement may be due to a reclassification.", "finding_ids": [rev["id"]]}]}
    assert pm.validate(json.dumps(hedged), ev)[0] is not None
    bad_id = {**good, "defender": [{"text": "Fine.", "finding_ids": ["nope"]}]}
    assert "unknown" in pm.validate(json.dumps(bad_id), ev)[1]
    verdict = {**good, "defender": [{"text": "You should hold on, it is a safe bet.", "finding_ids": [cash["id"]]}]}
    assert "advice or a verdict" in pm.validate(json.dumps(verdict), ev)[1]


def test_validator_rejects_multiplier_words_the_evidence_does_not_use(nwm):
    ev = pm.evidence_for(_findings(nwm.observations))
    debt = next(e for e in ev if e["id"].startswith("risk-debt"))
    good_def = [{"text": "Operating cash flow is still positive.", "finding_ids": [debt["id"]]}]
    bad = {"skeptic": [{"text": "Long-term debt more than doubled since 2021.", "finding_ids": [debt["id"]]}], "defender": good_def}
    assert "size claim" in pm.validate(json.dumps(bad), ev)[1]
    ok = {"skeptic": [{"text": "Long-term debt rose 62.5% since 2021.", "finding_ids": [debt["id"]]}], "defender": good_def}
    assert pm.validate(json.dumps(ok), ev)[0] is not None
