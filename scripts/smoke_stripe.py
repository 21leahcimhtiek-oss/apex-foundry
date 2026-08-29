"""Live smoke test: creates a REAL Stripe Checkout session (live keys).

Prints only non-secret results. Delete this file or keep out of CI.
"""

from fastapi.testclient import TestClient

from api.main import create_app

c = TestClient(create_app())
c.post(
    "/auth/register",
    json={"tenant_name": "SmokeTest", "email": "smoke-live@apex.test", "password": "supersecret1"},
)
tok = c.post(
    "/auth/token",
    data={"username": "smoke-live@apex.test", "password": "supersecret1"},
).json()["access_token"]
h = {"Authorization": "Bearer " + tok}

r = c.post("/billing/checkout/pro", headers=h)
print("checkout status:", r.status_code)
b = r.json()
if r.status_code == 200:
    print("checkout_url:", b.get("checkout_url", "")[:60])
    print("session_id:", b.get("session_id", "")[:24])
    print("mode: LIVE - a real Stripe Checkout session was created")
    sid = b.get("session_id", "")
    v = c.post("/billing/verify/" + sid, headers=h)
    print("verify status:", v.status_code, "| body:", v.json())
else:
    print("detail:", str(b.get("detail", ""))[:200])

r2 = c.get("/billing/plans")
print("plans endpoint:", r2.status_code, "plans:", len(r2.json()))
