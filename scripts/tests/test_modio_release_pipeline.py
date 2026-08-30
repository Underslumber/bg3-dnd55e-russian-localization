from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
ENV_EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")
PUBLISH = (ROOT / "scripts/publish-modio.ps1").read_text(encoding="utf-8-sig")
PUBLISH_UI = (ROOT / "scripts/publish-modio-ui.ps1").read_text(
    encoding="utf-8-sig"
)
PUBLISH_WEB = (ROOT / "scripts/publish-modio-web.mjs").read_text(encoding="utf-8")


def test_modio_only_dispatch_does_not_repeat_other_release_channels():
    assert "modio_version_tag:" in WORKFLOW
    assert "inputs.modio_version_tag != ''" in WORKFLOW
    assert "needs.build.result == 'skipped'" in WORKFLOW
    assert "needs.upload_to_nexusmods.result == 'skipped'" in WORKFLOW
    assert (
        "MODIO_VERSION_TAG: ${{ inputs.modio_version_tag || github.ref_name }}"
        in WORKFLOW
    )
    assert (
        "if: github.event_name == 'workflow_dispatch' && "
        "inputs.modio_version_tag != ''"
    ) in WORKFLOW
    assert "ref: ${{ inputs.modio_version_tag }}" in WORKFLOW
    assert "path: release-source" in WORKFLOW
    assert "-Workspace $publishWorkspace" in WORKFLOW
    assert "MODIO_BROWSER_PATH: ${{ vars.MODIO_BROWSER_PATH }}" in WORKFLOW
    assert "MODIO_BROWSER_PATH=" in ENV_EXAMPLE


def test_modio_browser_session_is_checked_before_toolkit_upload():
    preflight = PUBLISH.index(
        "Verifying the mod.io browser session before Toolkit upload"
    )
    toolkit_upload = PUBLISH.index("Toolkit GUI publish attempt")
    assert preflight < toolkit_upload
    assert "-WhatIf" in PUBLISH[preflight:toolkit_upload]
    assert "mod.io browser session preflight passed" in PUBLISH


def test_toolkit_transient_failures_have_bounded_recovery():
    assert "Open-ProjectSettingsByCoordinates" in PUBLISH_UI
    assert "refreshing Project Settings once before failing" in PUBLISH_UI
    assert "$guiMaxAttempts = 2" in PUBLISH
    assert "no mod.io upload handoff was reached" in PUBLISH
    assert "Toolkit did not hand off a new upload" not in PUBLISH[
        PUBLISH.index("$retryablePreUploadFailure") : PUBLISH.index(
            "if (-not $SkipModioApiFinalize)"
        )
    ]


def test_platform_selection_waits_for_react_state_to_settle():
    request = PUBLISH_WEB.index("const selectionRequest")
    settle = PUBLISH_WEB.index('waitFor("requested platform selection to settle"')
    save = PUBLISH_WEB.index('waitFor("enabled Save button"')
    assert request < settle < save
    assert "input.click()" in PUBLISH_WEB[request:settle]
    assert "input.disabled" in PUBLISH_WEB[request:settle]
    assert "Platform controls are missing" in PUBLISH_WEB[request:settle]

