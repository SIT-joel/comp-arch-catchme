"""Partner invitations and partnership lifecycle acceptance tests
(docs/DISCOVERY_PLAN.md): expiry, decline, duplicate requests, concurrent
acceptances, seeded-pair preservation through migration-shaped setup,
termination blocked-flow (sessions cancelled first), and the quest
boundary (discovery data never grants credit).
"""

import uuid
from datetime import timedelta

from tests.integration.conftest import login_as, set_profile
from tests.integration.test_discovery import (
    NOW,
    make_client,
    obs,
    provision_token,
    put_position,
)


def solo(api, solo_users):
    return {
        name: make_client(api, login_as(api, name, f"pw-{name}"))
        for name in solo_users
    }


def invite(client, to_user_id):
    return client.post("/api/v1/invitations", json={"to_user_id": str(to_user_id)})


def test_invitation_flow_and_expiry(api, solo_users, db_session, frozen_clock):
    clients = solo(api, solo_users)
    gamma, delta, epsilon = (solo_users[n] for n in ("gamma", "delta", "epsilon"))
    for u in (gamma, delta, epsilon):
        set_profile(db_session, u)

    # Self invitation rejected.
    assert invite(clients["gamma"], gamma.id).status_code == 422

    # Ineligible target (no shared interest) rejected.
    set_profile(db_session, epsilon, interests=("food",))
    assert invite(clients["gamma"], epsilon.id).status_code == 409

    created = invite(clients["gamma"], delta.id)
    assert created.status_code == 201
    invitation_id = created.json()["id"]

    # Duplicate pending invitation for the same pair rejected — in either
    # direction.
    assert invite(clients["gamma"], delta.id).status_code == 409
    assert invite(clients["delta"], gamma.id).status_code == 409

    listing = clients["delta"].get("/api/v1/invitations").json()
    assert [i["id"] for i in listing["incoming"]] == [invitation_id]
    assert listing["outgoing"] == []

    # Expiry at 5 minutes: lazy transition, then accept fails.
    frozen_clock.advance(301)
    listing = clients["delta"].get("/api/v1/invitations").json()
    assert listing["incoming"] == []
    response = clients["delta"].post(f"/api/v1/invitations/{invitation_id}/accept")
    assert response.status_code == 409

    # A fresh invitation can be accepted: partnership active on both sides.
    invitation_id = invite(clients["gamma"], delta.id).json()["id"]
    accepted = clients["delta"].post(f"/api/v1/invitations/{invitation_id}/accept")
    assert accepted.status_code == 200
    partnership_id = accepted.json()["id"]

    for name, uid in (("gamma", gamma.id), ("delta", delta.id)):
        out = clients[name].get("/api/v1/me/partnership").json()
        assert out["id"] == partnership_id
        assert uuid.UUID(out["partner"]["id"]) in (gamma.id, delta.id)
        assert uuid.UUID(out["partner"]["id"]) != uid

    # Partnered users disappear from third-party discovery immediately.
    set_profile(db_session, epsilon, interests=("gaming",))
    put_position(db_session, gamma, 52.52, 13.40, NOW)
    put_position(db_session, epsilon, 52.52, 13.40, NOW)
    out = clients["epsilon"].get("/api/v1/me/discovery").json()
    assert out["results"] == []

    # Accepting a session now works for the pair (existing quest flow).
    session = clients["gamma"].post(
        "/api/v1/sessions", json={"quest_id": "together", "demo": True}
    ).json()
    assert session["state"] == "pending"

    # Ending the partnership cancels pending/active sessions first.
    ended = clients["delta"].delete("/api/v1/me/partnership")
    assert ended.status_code == 200
    assert ended.json()["ended_at"] is not None

    from app.models import QuestSession

    db_session.expire_all()
    quest = db_session.get(QuestSession, uuid.UUID(session["id"]))
    assert quest.state == "cancelled"

    # Both unpaired again; partnership history preserved.
    for name in ("gamma", "delta"):
        assert clients[name].get("/api/v1/me/partnership").status_code == 404
    from app.models import Partnership, PartnershipMember

    members = (
        db_session.query(PartnershipMember)
        .filter(PartnershipMember.partnership_id == uuid.UUID(partnership_id))
        .all()
    )
    assert len(members) == 2 and all(m.left_at is not None for m in members)
    partnership = db_session.get(Partnership, uuid.UUID(partnership_id))
    assert partnership.ended_at is not None


def test_invitation_decline_and_idempotent_accept(api, solo_users, db_session, frozen_clock):
    clients = solo(api, solo_users)
    gamma, delta, epsilon = (solo_users[n] for n in ("gamma", "delta", "epsilon"))
    for u in (gamma, delta, epsilon):
        set_profile(db_session, u)

    invitation_id = invite(clients["gamma"], delta.id).json()["id"]
    declined = clients["delta"].post(f"/api/v1/invitations/{invitation_id}/decline")
    assert declined.status_code == 200
    assert declined.json()["status"] == "declined"
    # Double decline rejected.
    assert clients["delta"].post(
        f"/api/v1/invitations/{invitation_id}/decline").status_code == 409
    # Accepting a declined invitation rejected.
    assert clients["delta"].post(
        f"/api/v1/invitations/{invitation_id}/accept").status_code == 409
    # Only the recipient may respond.
    invitation_id = invite(clients["epsilon"], gamma.id).json()["id"]
    assert clients["delta"].post(
        f"/api/v1/invitations/{invitation_id}/accept").status_code == 403

    # Idempotent acceptance: retry returns the same partnership.
    invitation_id = invite(clients["gamma"], delta.id).json()["id"]
    first = clients["delta"].post(f"/api/v1/invitations/{invitation_id}/accept").json()
    again = clients["delta"].post(f"/api/v1/invitations/{invitation_id}/accept")
    assert again.status_code == 200 and again.json()["id"] == first["id"]
    assert clients["gamma"].get("/api/v1/me/partnership").json()["id"] == first["id"]

    # Acceptance requires eligibility to still hold: after ending, a retry
    # of the same (already accepted) invitation is a conflict, not a repair.
    clients["gamma"].delete("/api/v1/me/partnership")
    response = clients["delta"].post(f"/api/v1/invitations/{invitation_id}/accept")
    assert response.status_code == 409


def test_concurrent_acceptances_one_partnership(api, solo_users, db_session, frozen_clock):
    """Two overlapping invitations accepted concurrently on opposite
    pairing sides: the database partial unique index guarantees exactly one
    active membership per user."""
    import threading

    from app.db import SessionLocal
    from app.models import PartnershipMember

    clients = solo(api, solo_users)
    gamma, delta, epsilon = (solo_users[n] for n in ("gamma", "delta", "epsilon"))
    for u in (gamma, delta, epsilon):
        set_profile(db_session, u)

    inv_gd = invite(clients["gamma"], delta.id).json()["id"]
    inv_ed = invite(clients["epsilon"], delta.id).json()["id"]

    results = []

    def accept(client, invitation_id):
        # Fresh session per thread: FastAPI endpoints each open their own.
        response = client.post(f"/api/v1/invitations/{invitation_id}/accept")
        results.append((invitation_id, response.status_code))

    threads = [
        threading.Thread(target=accept, args=(clients["delta"], inv_gd)),
        threading.Thread(target=accept, args=(clients["delta"], inv_ed)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    statuses = sorted(s for _, s in results)
    assert statuses == [200, 409]  # exactly one wins

    db = SessionLocal()
    active = (
        db.query(PartnershipMember)
        .filter(PartnershipMember.left_at.is_(None))
        .all()
    )
    assert len(active) == 2  # one partnership, two members
    assert len({m.user_id for m in active}) == 2
    assert len({m.partnership_id for m in active}) == 1
    db.close()


def test_quest_boundary_discovery_never_grants_credit(api, solo_users, db_session, frozen_clock):
    """Discovery observations and cached positions must not become session
    heartbeat evidence or explore credit (docs/DISCOVERY_PLAN.md)."""
    clients = solo(api, solo_users)
    gamma, delta = solo_users["gamma"], solo_users["delta"]
    for u in (gamma, delta):
        set_profile(db_session, u)
    # Partner the two so the quest flow is available.
    invitation_id = invite(clients["gamma"], delta.id).json()["id"]
    clients["delta"].post(f"/api/v1/invitations/{invitation_id}/accept")

    # Live "discovery-grade" GPS: cached at 30 s freshness (stale for
    # explore's 10 s rule), plus BLE observations — but no session-bound
    # telemetry with peer evidence.
    put_position(db_session, gamma, 52.52, 13.40, NOW)
    put_position(db_session, delta, 52.52, 13.40, NOW)
    t_gamma = provision_token(db_session, gamma, 5000)
    t_delta = provision_token(db_session, delta, 5001)
    obs(clients["gamma"], 5001, NOW)
    obs(clients["delta"], 5000, NOW)

    session = clients["gamma"].post(
        "/api/v1/sessions", json={"quest_id": "together", "demo": True}).json()
    clients["delta"].post(f"/api/v1/sessions/{session['id']}/accept")

    listing = clients["gamma"].get("/api/v1/sessions").json()
    active = next(s for s in listing["sessions"] if s["id"] == session["id"])
    assert active["state"] == "active"
    assert active["progress_ms"] == 0  # no credit from discovery data

    from app.models import QuestAward

    assert db_session.query(QuestAward).count() == 0
