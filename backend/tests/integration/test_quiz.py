"""'Know Your Partner' quiz integration tests.

Flow: profile interests -> quiz session create/accept (activation generates
questions about the partner) -> per-question answers through the
authenticated phone -> completion awards exactly once (+100/+100).
"""


def _set_interests(client, tags):
    body = {"display_name": f"Tester {tags[0]}", "age": 25,
            "pref_min_age": 18, "pref_max_age": 99,
            "interests": list(tags), "radius_m": 500}
    r = client.put("/api/v1/me/discovery-profile", json=body)
    assert r.status_code == 200, r.text


def _start_quiz(clients):
    _set_interests(clients["a"], ["gaming", "music", "food"])
    _set_interests(clients["b"], ["travel", "reading"])
    created = clients["a"].post("/api/v1/sessions", json={"quest_id": "quiz", "demo": True})
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    accepted = clients["b"].post(f"/api/v1/sessions/{sid}/accept")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["state"] == "active"
    return sid


def test_quiz_generation_on_activation(clients):
    sid = _start_quiz(clients)
    # A answers about B: B has travel + reading -> 2 questions.
    state_a = clients["a"].get(f"/api/v1/sessions/{sid}/quiz").json()
    assert state_a["my_total"] == 2 and state_a["questions"] != []
    for q in state_a["questions"]:
        assert len(q["options"]) == 4 and len(set(q["options"])) == 4
        assert not q["answered"] and q["choice"] is None
        assert q["text"].startswith("Which of these is")
    # B answers about A: A has gaming + music + food -> 3 questions.
    state_b = clients["b"].get(f"/api/v1/sessions/{sid}/quiz").json()
    assert state_b["my_total"] == 3
    # Every question's correct option is within the subject's interests
    # (server-side check through the DB; the client payload has no flag).
    from app.models import QuizQuestion
    # (client payload carries no correct answer anywhere)
    assert "correct_index" not in state_a["questions"][0]


def test_quiz_answer_flow_and_exactly_once_award(clients):
    sid = _start_quiz(clients)
    me_before_a = clients["a"].get("/api/v1/me").json()["user"]
    me_before_b = clients["b"].get("/api/v1/me").json()["user"]

    # B answers their 3 questions about A — wrong answers are fine (score is
    # informational; the award pays on completion either way).
    state_b = clients["b"].get(f"/api/v1/sessions/{sid}/quiz").json()
    for q in state_b["questions"]:
        r = clients["b"].post(
            f"/api/v1/sessions/{sid}/quiz/answer",
            json={"question_index": q["index"], "choice": 0},
        )
        assert r.status_code == 200, r.text
        assert r.json()["questions"][q["index"]]["answered"] is True
        assert r.json()["questions"][q["index"]]["choice"] == 0

    # A has 2 questions (0,1); B's set has 3 — answering an index outside
    # your own set is 404 (only your own questions exist for you).
    foreign = clients["a"].post(
        f"/api/v1/sessions/{sid}/quiz/answer",
        json={"question_index": 2, "choice": 1},
    )
    assert foreign.status_code == 404

    # A answers their 2 questions -> all answered -> completion + award.
    me_a_after = clients["a"].get("/api/v1/me").json()["user"]
    state_a = clients["a"].get(f"/api/v1/sessions/{sid}/quiz").json()
    for q in state_a["questions"]:
        r = clients["a"].post(
            f"/api/v1/sessions/{sid}/quiz/answer",
            json={"question_index": q["index"], "choice": 2},
        )
        assert r.status_code == 200, r.text
    session = clients["a"].get(f"/api/v1/sessions/{sid}").json()
    assert session["state"] == "completed" and session["completed_at"]

    me_a = clients["a"].get("/api/v1/me").json()["user"]
    me_b = clients["b"].get("/api/v1/me").json()["user"]
    assert me_a["points"] == me_before_a["points"] + 100
    assert me_a["lifetime_xp"] == me_before_a["lifetime_xp"] + 100
    assert me_b["points"] == me_before_b["points"] + 100
    assert me_b["lifetime_xp"] == me_before_b["lifetime_xp"] + 100


def test_quiz_answer_on_completed_session_409(clients):
    sid = _start_quiz(clients)
    state_b = clients["b"].get(f"/api/v1/sessions/{sid}/quiz").json()
    for q in state_b["questions"]:
        clients["b"].post(
            f"/api/v1/sessions/{sid}/quiz/answer",
            json={"question_index": q["index"], "choice": 3},
        )
    state_a = clients["a"].get(f"/api/v1/sessions/{sid}/quiz").json()
    for q in state_a["questions"][:-1]:
        clients["a"].post(
            f"/api/v1/sessions/{sid}/quiz/answer",
            json={"question_index": q["index"], "choice": 1},
        )
    # Complete with the final answer, then confirm further answers 409.
    last = state_a["questions"][-1]
    done = clients["a"].post(
        f"/api/v1/sessions/{sid}/quiz/answer",
        json={"question_index": last["index"], "choice": 1},
    )
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["completed"] is True, body
    assert clients["a"].get(f"/api/v1/sessions/{sid}").json()["state"] == "completed"
    replay = clients["a"].post(
        f"/api/v1/sessions/{sid}/quiz/answer",
        json={"question_index": last["index"], "choice": 2},
    )
    assert replay.status_code == 409
    me_a = clients["a"].get("/api/v1/me").json()["user"]
    me_b = clients["b"].get("/api/v1/me").json()["user"]
    # Exactly once: one award transaction per player (clean_tables resets the
    # DB before each test, so totals start from zero).
    tx_all = clients["a"].get("/api/v1/transactions").json().get("transactions", [])
    txs_a = [t for t in tx_all if t["delta"] == 100]
    assert len(txs_a) == 1
    assert me_a["points"] == 100 and me_a["lifetime_xp"] == 100
    assert me_b["points"] == 100 and me_b["lifetime_xp"] == 100


def test_quiz_choice_validation(clients):
    sid = _start_quiz(clients)
    bad = clients["a"].post(
        f"/api/v1/sessions/{sid}/quiz/answer",
        json={"question_index": 0, "choice": 7},
    )
    assert bad.status_code == 422
    negative = clients["a"].post(
        f"/api/v1/sessions/{sid}/quiz/answer",
        json={"question_index": -1, "choice": 1},
    )
    assert negative.status_code == 422
    missing = clients["a"].post(
        f"/api/v1/sessions/{sid}/quiz/answer",
        json={"question_index": 99, "choice": 1},
    )
    assert missing.status_code == 404
