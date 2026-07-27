import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "check-upstream-change.py"
SPEC = importlib.util.spec_from_file_location("check_upstream_change", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_reads_and_decodes_parent_version64():
    raw = 145663330512535552
    xml = f"""
    <save>
      <region id="Config">
        <node id="root">
          <children>
            <node id="ModuleInfo">
              <attribute id="Version64" type="int64" value="{raw}" />
            </node>
          </children>
        </node>
      </region>
    </save>
    """.encode()

    parsed_raw, version = MODULE.read_parent_version(xml, "memory://parent-meta")
    assert parsed_raw == str(raw)
    assert version == "4.11.14.0"
