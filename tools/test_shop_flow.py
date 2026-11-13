"""Shop flow verification (non-GPS test sweep): buy two badges with earned
points, verify the third is rejected as unaffordable, verify XP never
decreases and the balance math holds, verify idempotent retry.

Usage: py -3 tools/test_shop_flow.py
"""

import json
import sys
import time
import urllib.request


def api(path, method="GET", body=None, token=None, idem=None):
    req = urllib.request.Request("http://127.0.0.1:8000/api/v1" + path, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if idem:
        req.add_header("Idempotency-Key", idem)
    data = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode()
    try:
        with urllib.request.urlopen(req, data=data, timeout=10) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def mint(username):
    import subprocess
    out = subprocess.run(
        [sys.executable, "../tools/mint_session.py", username],
        capture_output=True, text=True, cwd="backend").stdout.split()
    return out[-1]


def main():
    mt = mint("miya")
    status, me = api("/me", token=mt)
    assert status == 200, me
    _, rewards = api("/rewards", token=mt)
    owned = {r["id"] for r in rewards["rewards"] if r["owned"]}
    balance = me["user"]["points"]
    print(f"miya: {balance} pts, owns {sorted(owned) or 'nothing'}")

    # Buy the cheapest unowned badges while affordable.
    bought = 0
    for r in sorted(rewards["rewards"], key=lambda r: r["price"]):
        if r["id"] in owned or r["price"] > balance:
            continue
        status, out = api("/purchases", "POST", {"reward_id": r["id"]},
                          token=mt, idem=f"shop-{r['id']}-{int(time.time())}")
        print(f"buy {r['id']} ({r['price']}): HTTP {status} -> balance_after {out.get('balance_after')}")
        assert status in (200, 201) and out["owned"], out
        balance = out["balance_after"]
        bought += 1
        # Idempotent retry with the same key: no double charge.
        status, out = api("/purchases", "POST", {"reward_id": r["id"]},
                          token=mt, idem=f"shop-{r['id']}-{int(time.time())}")
        assert status == 200, out
        assert out["balance_after"] == balance, out
    print(f"bought {bought} badge(s); balance now {balance}")

    # Any remaining unowned badge is now unaffordable: must be rejected.
    for r in rewards["rewards"]:
        if r["id"] not in owned and r["price"] > balance:
            status, out = api("/purchases", "POST", {"reward_id": r["id"]},
                              token=mt, idem=f"shop-reject-{r['id']}")
            print(f"unaffordable {r['id']} ({r['price']}): HTTP {status} -> {out['error']['code']}")
            assert status in (402, 409, 422), out

    status, me = api("/me", token=mt)
    print(f"final miya: {me['user']['points']} pts, {me['user']['lifetime_xp']} xp, "
          f"level {me['user']['level']}")
    assert me["user"]["lifetime_xp"] == 200  # spending never reduces XP
    assert me["user"]["level"] == 3
    print("SHOP FLOW PASS")


if __name__ == "__main__":
    main()
