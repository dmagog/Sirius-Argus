"""pytest-bdd: единый вход (SSO) в ops-консоли через Keycloak (ADR-0012).

Сквозной OIDC authorization-code-flow реальным юзером ds: старт от сервиса → форма логина
Keycloak → POST ds/ds → возврат в сервис → проверяем аутентифицированную сессию.
Скип, если сервис/Keycloak/OIDC-клиент не подняты (нужен профиль full + keycloak-init).
"""
import os
import re

import httpx
import pytest
from pytest_bdd import given, scenarios, then, when

GRAFANA = os.environ.get("SIRIUS_GRAFANA_URL", "http://localhost:3000")
GITEA = os.environ.get("SIRIUS_GITEA_URL", "http://localhost:3001")
scenarios("sso.feature")

S = {}


def _probe_redirect(url, client_id):
    """Сервис должен редиректить на Keycloak с нашим client_id, иначе OIDC не настроен → скип."""
    try:
        r = httpx.get(url, follow_redirects=False, timeout=10)
    except Exception as e:  # сервис не поднят
        pytest.skip(f"сервис недоступен: {e}")
    loc = r.headers.get("location", "")
    if r.status_code not in (302, 303, 307) or f"client_id={client_id}" not in loc:
        pytest.skip(f"OIDC-вход не настроен/не поднят (status={r.status_code})")


def _oidc_login(client, start_url):
    """Старт от сервиса → форма Keycloak → POST ds/ds → редирект обратно в сервис (cookies в client)."""
    r = client.get(start_url)
    m = re.search(r'action="([^"]*login-actions/authenticate[^"]*)"', r.text)
    if not m:
        pytest.skip("форма логина Keycloak не найдена (realm/клиент не готовы?)")
    action = m.group(1).replace("&amp;", "&")
    # форсируем ВСЕ накопленные cookies: на одном хосте localhost:<порт> http.cookiejar строго
    # скоупит по path и роняет AUTH_SESSION_ID Keycloak на POST → KC 400 "Cookie not found".
    client.post(action, data={"username": "ds", "password": "ds", "credentialId": ""},
                cookies=dict(client.cookies))


# ---------------- Grafana ----------------
@given("Grafana с включённым OIDC-входом через Keycloak")
def grafana_oidc():
    _probe_redirect(f"{GRAFANA}/login/generic_oauth", "grafana")


@when("оператор ds проходит OIDC-вход в Grafana")
def grafana_login():
    with httpx.Client(follow_redirects=True, timeout=15) as c:
        _oidc_login(c, f"{GRAFANA}/login/generic_oauth")
        S["grafana_user"] = c.get(f"{GRAFANA}/api/user")  # 200+JSON если вошёл, 401 если нет


@then("Grafana-сессия принадлежит ds")
def grafana_is_ds():
    r = S["grafana_user"]
    assert r.status_code == 200, r.text
    ident = (r.json().get("login") or "") + (r.json().get("email") or "")
    assert "ds" in ident, f"ожидали сессию ds, получили: {r.text[:200]}"


# ---------------- Gitea ----------------
@given("Gitea с включённым OIDC-источником Keycloak")
def gitea_oidc():
    _probe_redirect(f"{GITEA}/user/oauth2/keycloak", "gitea")


@when("оператор ds проходит OIDC-вход в Gitea")
def gitea_login():
    with httpx.Client(follow_redirects=True, timeout=15) as c:
        _oidc_login(c, f"{GITEA}/user/oauth2/keycloak")
        # без follow: 200 = аутентифицирован, 3xx (редирект на /user/login) = не вошёл
        S["gitea_acct"] = c.get(f"{GITEA}/user/settings/account", follow_redirects=False)


@then("Gitea-сессия аутентифицирована")
def gitea_authed():
    r = S["gitea_acct"]
    assert r.status_code == 200, \
        f"ожидали аутентифицированную сессию (200), получили {r.status_code} (редирект = не вошёл)"
