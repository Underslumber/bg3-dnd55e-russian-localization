import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PUBLISH_WEB = (ROOT / "scripts/publish-modio-web.mjs").read_text(encoding="utf-8")


def _page_expression(function_name):
    start = PUBLISH_WEB.index(f"async function {function_name}()")
    match = re.search(r"evaluate\(String\.raw`([\s\S]*?)`\)", PUBLISH_WEB[start:])
    assert match, f"could not find page expression for {function_name}"
    return match.group(1)


READ_LOGIN_ACTION_STATE = _page_expression("readLoginActionState")
CLICK_SSO_ACTION = _page_expression("clickVisibleLarianSsoAction")


def _run_fixture(url, elements):
    fixture = {
        "url": url,
        "elements": [
            {
                "tagName": element.get("tag", "BUTTON"),
                "text": element.get("text", "Log in with Larian Studios"),
                "attrs": element.get("attrs", {}),
                "disabled": element.get("disabled", False),
                "hidden": element.get("hidden", False),
            }
            for element in elements
        ],
    }
    script = r"""
const input = JSON.parse(process.argv[1]);
global.location = { href: input.url };
global.getComputedStyle = (element) => ({
  visibility: element.hidden ? 'hidden' : 'visible',
  display: 'block', opacity: '1'
});
global.HTMLAnchorElement = class HTMLAnchorElement {};
const elements = input.elements.map((item) => {
  const element = {
    tagName: item.tagName,
    innerText: item.text,
    textContent: item.text,
    disabled: item.disabled,
    title: '',
    clicked: false,
    attrs: item.attrs,
    getAttribute(name) { return this.attrs[name] ?? null; },
    getBoundingClientRect() { return { width: this.hidden ? 0 : 100, height: this.hidden ? 0 : 20 }; },
    click() { this.clicked = true; }
  };
  element.hidden = item.hidden;
  if (item.tagName === 'A') {
    Object.setPrototypeOf(element, global.HTMLAnchorElement.prototype);
    Object.defineProperty(element, 'href', {
      get() { return new URL(this.getAttribute('href'), input.url).href; },
      set(value) { this.attrs.href = value; }
    });
  }
  return element;
});
global.document = {
  body: { innerText: '' },
  querySelectorAll(selector) {
    if (selector.startsWith('input') || selector.includes('captcha')) return [];
    return elements;
  }
};
const state = new Function(`return ${input.readExpression}`)();
const result = new Function(`return ${input.clickExpression}`)();
process.stdout.write(JSON.stringify({ state, result, clicked: elements.map((e) => e.clicked) }));
"""
    result = subprocess.run(
        [
            "node",
            "-e",
            script,
            json.dumps(
                {
                    **fixture,
                    "readExpression": READ_LOGIN_ACTION_STATE,
                    "clickExpression": CLICK_SSO_ACTION,
                }
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_larian_portal_button_without_href_is_counted_and_clicked_as_a_control():
    result = _run_fixture(
        "https://mod.io/g/baldursgate3?portal=studio",
        [{"tag": "BUTTON"}],
    )
    assert result["state"]["ssoCount"] == 1
    assert result["result"] == "clicked"
    assert result["clicked"] == [True]


def test_no_href_button_is_not_accepted_outside_the_exact_bg3_portal():
    for url in (
        "https://mod.io/login",
        "https://mod.io/g/baldursgate3/m/dnd-55e-all-in-one-beyond-russian-localization/admin/settings",
        "https://example.com/g/baldursgate3?portal=studio",
    ):
        result = _run_fixture(url, [{"tag": "BUTTON"}])
        assert result["state"]["ssoCount"] == 0
        assert result["result"] != "clicked"


def test_unsafe_and_ambiguous_actions_are_rejected():
    unsafe = _run_fixture(
        "https://mod.io/g/baldursgate3?portal=studio",
        [{"tag": "A", "attrs": {"href": "https://evil.example/sso"}}],
    )
    assert unsafe["state"]["ssoCount"] == 0
    assert unsafe["result"] == "invalid_target"

    ambiguous = _run_fixture(
        "https://mod.io/g/baldursgate3?portal=studio",
        [{"tag": "BUTTON"}, {"tag": "BUTTON"}],
    )
    assert ambiguous["state"]["ssoCount"] == 2
    assert ambiguous["result"] == "ambiguous"
    assert ambiguous["clicked"] == [False, False]


def test_hidden_and_disabled_actions_are_not_selected():
    for element in ({"tag": "BUTTON", "hidden": True}, {"tag": "BUTTON", "disabled": True}):
        result = _run_fixture("https://mod.io/g/baldursgate3?portal=studio", [element])
        assert result["state"]["ssoCount"] == 0
        assert result["result"] == "missing"
        assert result["clicked"] == [False]


def test_existing_link_action_and_safe_larian_anchor_behavior_is_preserved():
    link_action = _run_fixture(
        "https://mod.io/g/baldursgate3?portal=studio",
        [{"tag": "BUTTON", "text": "Link your Larian Studios account"}],
    )
    assert link_action["state"]["ssoCount"] == 1
    assert link_action["result"] == "clicked"

    anchor = _run_fixture(
        "https://mod.io/g/baldursgate3?portal=studio",
        [{"tag": "A", "attrs": {"href": "https://larian.com/account/login"}}],
    )
    assert anchor["state"]["ssoCount"] == 1
    assert anchor["result"] == "clicked"
    assert anchor["clicked"] == [True]
