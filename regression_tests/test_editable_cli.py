import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_ppt import create_argument_parser, resolve_editable_scene_dir


def test_editable_flags_default_off():
    args = create_argument_parser().parse_args([])
    assert args.editable is False
    assert args.editable_scenes is None


def test_editable_flags_parse_explicit_directory():
    args = create_argument_parser().parse_args(["--editable", "--editable-scenes", "scenes"])
    assert args.editable is True
    assert args.editable_scenes == "scenes"


def test_scene_resolver_does_nothing_when_editable_is_off(tmp_path):
    args = SimpleNamespace(editable=False, editable_scenes=str(tmp_path / "missing"))
    assert resolve_editable_scene_dir(args, tmp_path / "output") is None


def test_scene_resolver_prefers_explicit_directory(tmp_path):
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    args = SimpleNamespace(editable=True, editable_scenes=str(explicit))
    assert resolve_editable_scene_dir(args, tmp_path / "output") == explicit


def test_scene_resolver_falls_back_to_session_directory(tmp_path):
    fallback = tmp_path / "output" / "editable_scenes"
    fallback.mkdir(parents=True)
    args = SimpleNamespace(editable=True, editable_scenes=None)
    assert resolve_editable_scene_dir(args, tmp_path / "output") == fallback


def test_scene_resolver_reports_actionable_missing_directory(tmp_path):
    args = SimpleNamespace(editable=True, editable_scenes=None)
    with pytest.raises(ValueError, match="--editable-scenes"):
        resolve_editable_scene_dir(args, tmp_path / "output")
