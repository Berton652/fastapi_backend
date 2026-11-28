import uuid

from app.config import get_settings
from app.models import Provider
from app.services.conversion import quote

from .conftest import PASSWORD, register_and_login


def balances(client, headers):
    return {w["provider"]: w["balance"] for w in client.get("/wallets", headers=headers).json()}


def top_up(client, headers, provider, amount):
    r = client.post("/wallets/top-up", json={"provider": provider, "amount": amount}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ---- auth ---------------------------------------------------------------------

def test_register_returns_user_and_creates_four_zero_wallets(client):
    r = client.post(
        "/auth/register",
        json={"email": "A@Example.com", "full_name": "  Amara  ", "password": PASSWORD, "phone_number": "+23276000000"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "a@example.com" and body["full_name"] == "Amara"
    assert body["role"] == "user" and body["is_active"] is True and body["is_verified"] is False

    _, h = register_and_login(client, "b@example.com")
    wallets = client.get("/wallets", headers=h).json()
    assert [w["provider"] for w in wallets] == ["QMONEY", "ORANGE_MONEY", "AFRIMONEY", "USD"]
    assert [w["currency_code"] for w in wallets] == ["SLL", "SLL", "SLL", "USD"]
    assert all(w["balance"] == 0 for w in wallets)


def test_duplicate_email_conflicts(client):
    register_and_login(client)
    r = client.post("/auth/register", json={"email": "AMARA@example.com", "full_name": "X", "password": PASSWORD})
    assert r.status_code == 409 and isinstance(r.json()["detail"], str)


def test_weak_password_error_is_a_plain_string(client):
    r = client.post("/auth/register", json={"email": "a@example.com", "full_name": "A", "password": "short"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, str) and "at least 10 characters" in detail


def test_login_wrong_password_and_unknown_user_look_identical(client):
    register_and_login(client)
    bad_pw = client.post("/auth/login", json={"email": "amara@example.com", "password": "Wrong!Passw0rd"})
    no_user = client.post("/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert bad_pw.status_code == no_user.status_code == 401
    assert bad_pw.json() == no_user.json()


def test_very_long_password_is_supported(client):
    pw = "Aa1!" + "x" * 200
    assert client.post("/auth/register", json={"email": "l@example.com", "full_name": "L", "password": pw}).status_code == 201
    assert client.post("/auth/login", json={"email": "l@example.com", "password": pw}).status_code == 200


def test_missing_or_garbage_token_is_401_not_403(client):
    assert client.get("/wallets").status_code == 401
    assert client.get("/wallets", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_refresh_token_cannot_be_used_as_access_token(client):
    tokens, _ = register_and_login(client)
    r = client.get("/wallets", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert r.status_code == 401


def test_refresh_rotates_and_replay_revokes_everything(client):
    tokens, _ = register_and_login(client)
    r1 = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r1.status_code == 200
    new = r1.json()
    assert new["refresh_token"] != tokens["refresh_token"]

    # Replaying the old (rotated-out) token fails AND burns the new one too.
    assert client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": new["refresh_token"]}).status_code == 401


def test_logout_revokes_refresh_token(client):
    tokens, _ = register_and_login(client)
    assert client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]}).status_code == 204
    assert client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


# ---- wallets ------------------------------------------------------------------

def test_top_up_and_validation(client):
    _, h = register_and_login(client)
    assert top_up(client, h, "USD", 50)["balance"] == 50
    assert top_up(client, h, "USD", 0.5)["balance"] == 50.5
    for bad in (0, -5, 1.234):
        r = client.post("/wallets/top-up", json={"provider": "USD", "amount": bad}, headers=h)
        assert r.status_code == 422, bad
    r = client.post("/wallets/top-up", json={"provider": "BITCOIN", "amount": 5}, headers=h)
    assert r.status_code == 422


def test_top_up_can_be_disabled(client, monkeypatch):
    _, h = register_and_login(client)
    monkeypatch.setenv("ONEPOINT_ALLOW_SIMULATED_TOPUP", "false")
    get_settings.cache_clear()
    try:
        r = client.post("/wallets/top-up", json={"provider": "USD", "amount": 5}, headers=h)
        assert r.status_code == 403
    finally:
        monkeypatch.delenv("ONEPOINT_ALLOW_SIMULATED_TOPUP")
        get_settings.cache_clear()


def test_users_cannot_see_each_others_wallets(client):
    _, h1 = register_and_login(client, "one@example.com")
    _, h2 = register_and_login(client, "two@example.com")
    top_up(client, h1, "USD", 99)
    assert balances(client, h2)["USD"] == 0


# ---- conversions --------------------------------------------------------------

def convert(client, headers, src, dst, amount, key=None):
    return client.post(
        "/conversions",
        json={"from_provider": src, "to_provider": dst, "amount": amount, "idempotency_key": key or str(uuid.uuid4())},
        headers=headers,
    )


def test_usd_to_sll_matches_app_preview(client):
    _, h = register_and_login(client)
    top_up(client, h, "USD", 50)
    r = convert(client, h, "USD", "QMONEY", 50)
    assert r.status_code == 201
    tx = r.json()
    # 50 USD * 22.5 = 1125.00 gross, 2% fee = 22.50, credited 1102.50
    assert tx["amount_debited"] == 50 and tx["fee_amount"] == 22.5 and tx["amount_credited"] == 1102.5
    assert tx["exchange_rate"] == 22.5 and tx["status"] == "COMPLETED"
    b = balances(client, h)
    assert b["USD"] == 0 and b["QMONEY"] == 1102.5


def test_sll_to_usd_and_sll_to_sll(client):
    _, h = register_and_login(client)
    top_up(client, h, "QMONEY", 10000)
    tx = convert(client, h, "QMONEY", "USD", 450).json()
    # 450 / 22.5 = 20.00 gross, 2% fee = 0.40, credited 19.60
    assert (tx["fee_amount"], tx["amount_credited"]) == (0.4, 19.6)
    tx = convert(client, h, "QMONEY", "ORANGE_MONEY", 1000).json()
    assert (tx["exchange_rate"], tx["fee_amount"], tx["amount_credited"]) == (1.0, 10.0, 990.0)


def test_credited_plus_fee_always_equals_gross():
    s = get_settings()
    for amt in ("0.07", "1", "3.33", "999999.99", "12345.67"):
        for src, dst in [(Provider.USD, Provider.QMONEY), (Provider.QMONEY, Provider.USD), (Provider.QMONEY, Provider.AFRIMONEY)]:
            from decimal import Decimal
            q = quote(s, src, dst, Decimal(amt))
            assert q.credited + q.fee == q.gross


def test_insufficient_funds_changes_nothing(client):
    _, h = register_and_login(client)
    top_up(client, h, "QMONEY", 100)
    r = convert(client, h, "QMONEY", "ORANGE_MONEY", 100.01)
    assert r.status_code == 400 and "Insufficient" in r.json()["detail"]
    assert balances(client, h)["QMONEY"] == 100
    assert client.get("/conversions", headers=h).json() == []


def test_same_wallet_rejected(client):
    _, h = register_and_login(client)
    top_up(client, h, "USD", 10)
    assert convert(client, h, "USD", "USD", 5).status_code == 400


def test_idempotent_replay_moves_money_once(client):
    _, h = register_and_login(client)
    top_up(client, h, "QMONEY", 1000)
    key = str(uuid.uuid4())
    first = convert(client, h, "QMONEY", "ORANGE_MONEY", 400, key)
    again = convert(client, h, "QMONEY", "ORANGE_MONEY", 400, key)
    assert first.status_code == again.status_code == 201
    assert first.json()["id"] == again.json()["id"]
    b = balances(client, h)
    assert b["QMONEY"] == 600 and b["ORANGE_MONEY"] == 396
    assert len(client.get("/conversions", headers=h).json()) == 1


def test_idempotency_key_reuse_with_different_params_is_409(client):
    _, h = register_and_login(client)
    top_up(client, h, "QMONEY", 1000)
    key = str(uuid.uuid4())
    assert convert(client, h, "QMONEY", "ORANGE_MONEY", 400, key).status_code == 201
    assert convert(client, h, "QMONEY", "ORANGE_MONEY", 500, key).status_code == 409
    assert balances(client, h)["QMONEY"] == 600


def test_history_newest_first_and_requires_auth(client):
    _, h = register_and_login(client)
    top_up(client, h, "QMONEY", 1000)
    a = convert(client, h, "QMONEY", "ORANGE_MONEY", 100).json()["id"]
    b = convert(client, h, "QMONEY", "AFRIMONEY", 100).json()["id"]
    assert [t["id"] for t in client.get("/conversions", headers=h).json()] == [b, a]
    assert client.get("/conversions").status_code == 401
