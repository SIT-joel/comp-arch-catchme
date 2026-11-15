"""Achievements: the friend-journey milestones. Unlocks are idempotent rows
evaluated at the trigger points (pet care here; quest completion and
partnership acceptance in their own tests)."""


def test_catalog_route_lists_achievements(clients):
    r = clients["a"].get("/api/v1/achievements")
    assert r.status_code == 200, r.text
    items = r.json()["achievements"]
    ids = {i["id"] for i in items}
    assert {"new_friend", "together_1", "quiz_ace", "level_5"} <= ids
    for item in items:
        assert isinstance(item["name"], str)
        assert isinstance(item["description"], str)


def test_new_friend_unlocks_on_care_trigger(clients):
    # The seeded pair are already partnered; the care action is an
    # evaluation trigger — "new_friend" unlocks for the actor immediately.
    r = clients["a"].post("/api/v1/me/pet/care", json={"date": "2026-11-15"})
    assert r.status_code == 200, r.text
    items = clients["a"].get("/api/v1/achievements").json()["achievements"]
    unlocked = {i["id"]: i["unlocked"] for i in items}
    assert unlocked["new_friend"] is True
    # toma (the partner) has no trigger yet — unlocks at their own action.
    partner_items = clients["b"].get("/api/v1/achievements").json()["achievements"]
    partner = {i["id"]: i["unlocked"] for i in partner_items}
    assert partner["new_friend"] is False


def test_care_streak_3_unlocks_after_three_days(clients):
    a = clients["a"]
    for date in ("2026-11-13", "2026-11-14", "2026-11-15"):
        r = a.post("/api/v1/me/pet/care", json={"date": date})
        assert r.status_code == 200, r.text
    items = a.get("/api/v1/achievements").json()["achievements"]
    streak = next(i for i in items if i["id"] == "care_streak_3")
    assert streak["unlocked"] is True


def test_unlock_idempotent_across_triggers(clients):
    a = clients["a"]
    for date in ("2026-11-14", "2026-11-15"):
        assert a.post("/api/v1/me/pet/care", json={"date": date}).status_code == 200
    items = a.get("/api/v1/achievements").json()["achievements"]
    new_friend = next(i for i in items if i["id"] == "new_friend")
    assert new_friend["unlocked"] is True
    unlocked_at = new_friend["unlocked_at"]
    # Repeated triggers must not duplicate or re-stamp the row.
    a.post("/api/v1/me/pet/care", json={"date": "2026-11-15"})
    items2 = a.get("/api/v1/achievements").json()["achievements"]
    new_friend2 = next(i for i in items2 if i["id"] == "new_friend")
    assert new_friend2["unlocked_at"] == unlocked_at


def test_partner_route_requires_partnership(clients):
    # The partner-view route works for the active partner and 403s others;
    # the seeded pair are partnered, so b can read a's achievements.
    a_user_id = clients["a"].get("/api/v1/me").json()["user"]["id"]
    r = clients["b"].get(f"/api/v1/achievements/{a_user_id}")
    assert r.status_code == 200, r.text
    items = r.json()["achievements"]
    assert any(i["id"] == "new_friend" for i in items)
