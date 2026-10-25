import json

from fastapi.testclient import TestClient

from app.decisions.board import _sentence, build, size_band
from app.financial_data.companies import find_company
from app.main import app


def test_blind_view_leaks_no_identity_and_reveal_reflects():
    with TestClient(app) as c:
        r = c.post("/api/board", json={"tickers": ["NWM", "CSR"], "data_mode": "sample", "prior_pick": "CSR"})
        assert r.status_code == 201
        board = r.json()
        blob = json.dumps(board).lower()
        for leak in ("northwind", "contoso", "nwm", "csr", "sample-nwm", "sample-csr", "0000"):
            assert leak not in blob, leak
        assert board["labels"] == ["A", "B"] and "companies" not in board
        rev = {row["metric"]: row for row in board["rows"]}
        assert {cell["fmt"] for cell in rev["revenue"]["cells"].values()} == {"$10B to $100B"}
        assert all(cell["period"] in (None, "last 3 fiscal years") or cell["period"].startswith("FY") for row in board["rows"] for cell in row["cells"].values())
        nwm_label = next(lab for lab, cell in rev["cash_conversion"]["cells"].items() if cell["fmt"] == "0.61x")
        out = c.post(f"/api/board/{board['id']}/reveal", json={"pick": nwm_label}).json()
        assert out["companies"][nwm_label]["ticker"] == "NWM"
        assert "expected Contoso Retail" in out["reflection"]["text"] and "name may have been shaping" in out["reflection"]["text"]
        assert out["companies"][nwm_label]["evidence"]["cash_conversion"]  # evidence unlocked after reveal
        again = c.post(f"/api/board/{board['id']}/reveal", json={"pick": "A"}).json()
        assert again["pick"] == nwm_label  # a reveal can't be redone to change the pick


def test_board_validation():
    with TestClient(app) as c:
        assert c.post("/api/board", json={"tickers": ["NWM"], "data_mode": "sample"}).status_code == 422
        assert c.post("/api/board", json={"tickers": ["NWM", "NWM"], "data_mode": "sample"}).status_code == 422
        assert c.post("/api/board", json={"tickers": ["NWM", "ZZZZ"], "data_mode": "sample"}).status_code == 404


def test_neutral_sentences_and_bands():
    assert size_band(5e8) == "Under $1B" and size_band(2e11) == "Over $100B"
    s = _sentence("cash_conversion", {"A": 1.4, "B": 0.61, "C": None})
    assert s.startswith("A turns $1.40 of every $1 of profit into operating cash; B turns $0.61.") and "No figure for C" in s
    for word in ("better", "worse", "best", "worst", "buy", "sell"):
        assert word not in _sentence("debt_to_ocf", {"A": 0.4, "B": 7.2}).lower()


def test_labels_are_shuffled_server_side(nwm, csr):
    seen = set()
    for _ in range(30):
        b = build([{"company": find_company("NWM"), "observations": nwm.observations, "mode_used": "sample"},
                   {"company": find_company("CSR"), "observations": csr.observations, "mode_used": "sample"}], "sample", None)
        seen.add(b["companies"]["A"]["ticker"])
    assert seen == {"NWM", "CSR"}
