import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/publish-modio-web.mjs"
SOURCE = SCRIPT.read_text(encoding="utf-8")
SELECTOR = SOURCE.split("// TARGET_SELECTOR_START", 1)[1].split(
    "// TARGET_SELECTOR_END", 1
)[0]


def run_selector(target_sets):
    harness = f"""
{SELECTOR}
const targetSets = JSON.parse(process.argv[1]);
const results = targetSets.map((targets) => {{
  try {{ const target = selectModioTarget(
    targets,
    'https://mod.io/g/baldursgate3/m/dnd-55e-all-in-one-beyond-russian-localization/admin/settings#files',
    'https://mod.io/g/baldursgate3?portal=studio'
  ); return {{ id: target.id, url: target.url }}; }}
  catch (error) {{ return {{ error: error.message }}; }}
}});
process.stdout.write(JSON.stringify(results));
"""
    completed = subprocess.run(
        ["node", "-e", harness, json.dumps(target_sets)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def page(target_id, url, *, target_type="page"):
    return {
        "id": target_id,
        "type": target_type,
        "url": url,
        "webSocketDebuggerUrl": f"ws://127.0.0.1:9222/devtools/page/{target_id}",
    }


ADMIN = (
    "https://mod.io/g/baldursgate3/m/"
    "dnd-55e-all-in-one-beyond-russian-localization/admin/settings#files"
)
PROFILE = (
    "https://mod.io/g/baldursgate3/m/"
    "dnd-55e-all-in-one-beyond-russian-localization"
)
PORTAL = "https://mod.io/g/baldursgate3?portal=studio"


def test_prefers_requested_admin_and_ignores_unrelated_modio_pages():
    result = run_selector(
        [[
            page("public", PROFILE),
            page("admin", ADMIN),
            page("other-mod", "https://mod.io/g/baldursgate3/m/some-other-mod"),
            page("http-admin", ADMIN.replace("https:", "http:")),
        ]]
    )
    assert result == [{"id": "admin", "url": ADMIN}]


def test_reuses_safe_fallbacks_only_when_requested_admin_is_absent():
    result = run_selector(
        [
            [page("portal", PORTAL), page("profile", PROFILE)],
            [page("portal", PORTAL)],
        ]
    )
    assert result == [
        {"id": "profile", "url": PROFILE},
        {"id": "portal", "url": PORTAL},
    ]


def test_multiple_matching_admin_pages_use_stable_target_id_order():
    result = run_selector([[page("z-admin", ADMIN), page("a-admin", ADMIN)]])
    assert result == [{"id": "a-admin", "url": ADMIN}]


def test_login_and_signin_are_last_resort_fallbacks_with_query_preserved():
    login = "https://mod.io/login?return_to=%2Fg%2Fbaldursgate3&state=oauth-1"
    signin = "https://mod.io/signin?continue=%2Faccount&state=oauth-2"
    result = run_selector(
        [
            [page("login", login), page("signin", signin)],
            [page("signin-only", signin)],
            [page("profile", PROFILE), page("login", login)],
            [page("portal", PORTAL), page("login", login)],
        ]
    )
    assert result == [
        {"id": "login", "url": login},
        {"id": "signin-only", "url": signin},
        {"id": "profile", "url": PROFILE},
        {"id": "portal", "url": PORTAL},
    ]


def test_ambiguous_duplicate_ids_and_unsafe_only_targets_fail_closed():
    result = run_selector(
        [
            [page("same", ADMIN), page("same", ADMIN)],
            [page("http", ADMIN.replace("https:", "http:"))],
            [page("bad-port", ADMIN.replace("mod.io/", "mod.io:444/"))],
            [page("credentialed", "https://user:pass@mod.io/login?state=x")],
            [page("lookalike", "https://mod.io.attacker.example/login")],
            [page("nested-login", "https://mod.io/login/continue?state=x")],
            [page("external", "https://example.com/")],
            [page("devtools", ADMIN, target_type="service_worker")],
        ]
    )
    assert result[0]["error"] == (
        "Multiple matching mod.io browser pages do not have unique target IDs."
    )
    assert all("No existing trusted mod.io" in item["error"] for item in result[1:])
