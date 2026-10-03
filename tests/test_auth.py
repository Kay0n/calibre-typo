from __future__ import annotations

from calibre_typo.db import Database
from calibre_typo.services import admin
from conftest import ADMIN_PASSWORD, csrf


def test_fresh_install_redirects_to_setup(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/setup")


def test_setup_accepts_any_password(client):
    response = client.post("/setup", data={"csrf_token": csrf(client), "password": "a", "confirm": "a"})
    assert response.status_code == 302


def test_empty_password_turns_login_off(app, client):
    client.post("/setup", data={"csrf_token": csrf(client), "password": "", "confirm": ""})
    visitor = app.test_client()
    page = visitor.get("/")
    assert page.status_code == 200 and b"Log out" not in page.data
    assert visitor.get("/login").headers["Location"] == "/"
    # Still protected by CSRF and device tokens
    assert visitor.post("/devices/", data={"name": "Sneaky"}).status_code == 400
    assert visitor.get("/api/v1/ping").status_code == 401


def test_setting_a_password_turns_login_back_on(app, client):
    client.post("/setup", data={"csrf_token": csrf(client), "password": "", "confirm": ""})
    client.post("/account", data={"csrf_token": csrf(client), "password": ADMIN_PASSWORD, "confirm": ADMIN_PASSWORD})
    assert app.test_client().get("/").status_code == 302
    assert client.get("/").status_code == 200  # the browser that set it stays logged in


def test_setup_can_only_be_claimed_once(app, admin_client):
    late = app.test_client()
    response = late.post("/setup", data={"csrf_token": csrf(late),
                                         "password": "someone else's", "confirm": "someone else's"})
    assert response.headers["Location"].endswith("/login")
    assert late.post("/login", data={"csrf_token": csrf(late), "password": "someone else's"}).status_code == 200


def test_setup_logs_in_and_closes_setup(admin_client):
    assert admin_client.get("/").status_code == 200
    assert admin_client.get("/setup").headers["Location"].endswith("/login")


def test_login_and_logout(app, admin_client):
    admin_client.post("/logout", data={"csrf_token": csrf(admin_client)})
    assert admin_client.get("/").status_code == 302

    bad = admin_client.post("/login", data={"csrf_token": csrf(admin_client), "password": "nope"})
    assert b"Wrong password" in bad.data

    good = admin_client.post("/login", data={"csrf_token": csrf(admin_client), "password": ADMIN_PASSWORD})
    assert good.status_code == 302
    assert admin_client.get("/").status_code == 200


def test_post_without_csrf_token_is_refused(admin_client):
    assert admin_client.post("/devices/", data={"name": "Sneaky"}).status_code == 400


def login_from(client, address: str, password: str, forwarded_for: str | None = None):
    headers = {"X-Forwarded-For": forwarded_for} if forwarded_for else {}
    return client.post("/login", data={"csrf_token": csrf(client), "password": password},
                       headers=headers, environ_overrides={"REMOTE_ADDR": address})


def test_one_address_is_blocked_without_locking_out_others(app, admin_client):
    admin_client.post("/logout", data={"csrf_token": csrf(admin_client)})
    for _ in range(5):
        login_from(admin_client, "127.0.0.1", "nope", forwarded_for="203.0.113.9")
    blocked = login_from(admin_client, "127.0.0.1", ADMIN_PASSWORD, forwarded_for="203.0.113.9")
    assert b"Too many failed attempts" in blocked.data

    me = app.test_client()
    assert login_from(me, "127.0.0.1", ADMIN_PASSWORD, forwarded_for="198.51.100.4").status_code == 302


def test_forged_forwarded_for_entries_are_ignored(app, admin_client):
    admin_client.post("/logout", data={"csrf_token": csrf(admin_client)})
    for n in range(5):
        login_from(admin_client, "172.17.0.1", "nope", forwarded_for=f"10.0.0.{n}, 203.0.113.9")
    blocked = login_from(admin_client, "172.17.0.1", ADMIN_PASSWORD, forwarded_for="1.1.1.1, 203.0.113.9")
    assert b"Too many failed attempts" in blocked.data


def test_header_is_ignored_without_a_proxy(app, admin_client):
    admin_client.post("/logout", data={"csrf_token": csrf(admin_client)})
    public_peer = "8.8.4.4"  # documentation ranges like 203.0.113.0/24 count as private
    for n in range(5):
        login_from(admin_client, public_peer, "nope", forwarded_for=f"198.51.100.{n}")
    blocked = login_from(admin_client, public_peer, ADMIN_PASSWORD, forwarded_for="198.51.100.77")
    assert b"Too many failed attempts" in blocked.data


def test_failures_from_many_addresses_dont_lock_the_admin_out(app, admin_client):
    admin_client.post("/logout", data={"csrf_token": csrf(admin_client)})
    for n in range(60):  # more than any global limit would allow
        login_from(admin_client, f"8.8.{n}.1", "nope")
    assert login_from(app.test_client(), "1.2.3.4", ADMIN_PASSWORD).status_code == 302


def test_password_change_signs_out_other_sessions(app, admin_client):
    other = app.test_client()
    other.post("/login", data={"csrf_token": csrf(other), "password": ADMIN_PASSWORD})
    assert other.get("/").status_code == 200

    new_password = "an even longer password"
    admin_client.post("/account", data={"csrf_token": csrf(admin_client), "current": ADMIN_PASSWORD,
                                        "password": new_password, "confirm": new_password})
    assert admin_client.get("/").status_code == 200
    assert other.get("/").status_code == 302


def test_login_only_redirects_to_local_paths(admin_client):
    admin_client.post("/logout", data={"csrf_token": csrf(admin_client)})
    for target in ("//evil.example", "/\\evil.example", "https://evil.example", "/\t/evil.example",
                   "/\n/evil.example", "/\\/evil.example"):
        response = admin_client.post("/login", data={"csrf_token": csrf(admin_client), "next": target,
                                                     "password": ADMIN_PASSWORD})
        assert response.headers["Location"] == "/", target
        admin_client.post("/logout", data={"csrf_token": csrf(admin_client)})


def test_pages_send_security_headers(client):
    response = client.get("/login", follow_redirects=True)
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_claim_keeps_the_first_password(settings):
    """Direct, as the web flow redirects before a second claim can race"""
    db = Database(settings.database_path)
    db.migrate()
    with db.connect() as conn:
        assert admin.claim(conn, "first password")
        assert not admin.claim(conn, "second password")
        assert admin.verify_password(conn, "first password")


def test_logout_ends_the_session_even_for_a_copied_cookie(app, admin_client):
    copied = admin_client.get_cookie("calibre_typo_session").value
    admin_client.post("/logout", data={"csrf_token": csrf(admin_client)})
    thief = app.test_client()
    thief.set_cookie("calibre_typo_session", copied)
    assert thief.get("/").status_code == 302


def test_login_keeps_local_paths(admin_client):
    admin_client.post("/logout", data={"csrf_token": csrf(admin_client)})
    response = admin_client.post("/login", data={"csrf_token": csrf(admin_client), "next": "/books/1?x=1",
                                                 "password": ADMIN_PASSWORD})
    assert response.headers["Location"] == "/books/1?x=1"
