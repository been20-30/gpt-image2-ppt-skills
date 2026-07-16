from pathlib import Path
from types import SimpleNamespace

from scripts import render_template
from scripts.render_template import (
    _cleanup_keynote_export,
    _collect_keynote_export_pages,
)


def _write_png_stub(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"png")
    return path


def test_collects_keynote_directory_export(tmp_path):
    prefix = tmp_path / "_keynote_export.png"
    first = _write_png_stub(prefix / "_keynote_export.png.001.png")
    second = _write_png_stub(prefix / "_keynote_export.png.002.png")

    assert _collect_keynote_export_pages(prefix, 2) == [(1, first), (2, second)]


def test_collects_keynote_sibling_export(tmp_path):
    prefix = tmp_path / "_keynote_export.png"
    first = _write_png_stub(tmp_path / "_keynote_export.png.001.png")
    second = _write_png_stub(tmp_path / "_keynote_export.png.002.png")

    assert _collect_keynote_export_pages(prefix, 2) == [(1, first), (2, second)]


def test_accepts_direct_single_slide_export(tmp_path):
    prefix = _write_png_stub(tmp_path / "_keynote_export.png")

    assert _collect_keynote_export_pages(prefix, 1) == [(1, prefix)]


def test_rejects_missing_or_duplicate_keynote_pages(tmp_path):
    prefix = tmp_path / "_keynote_export.png"
    _write_png_stub(prefix / "_keynote_export.png.001.png")
    _write_png_stub(prefix / "duplicate.001.png")

    assert _collect_keynote_export_pages(prefix, 2) is None


def test_cleanup_removes_only_keynote_temporary_exports(tmp_path):
    prefix = tmp_path / "_keynote_export.png"
    _write_png_stub(prefix / "_keynote_export.png.001.png")
    sibling = _write_png_stub(tmp_path / "_keynote_export.png.002.png")
    final_page = _write_png_stub(tmp_path / "page-01.png")

    _cleanup_keynote_export(prefix)

    assert not prefix.exists()
    assert not sibling.exists()
    assert final_page.exists()


def test_keynote_render_uses_opened_document_and_collects_nested_pages(tmp_path, monkeypatch):
    pptx = tmp_path / "two slides 中文.pptx"
    pptx.write_bytes(b"pptx")
    output = tmp_path / "renders with spaces"

    monkeypatch.setattr(render_template.sys, "platform", "darwin")
    monkeypatch.setattr(
        render_template.os.path,
        "isdir",
        lambda path: path == "/Applications/Keynote.app",
    )

    def fake_run(command, **kwargs):
        script = command[2]
        assert "set theDoc to open POSIX file" in script
        assert "front document" not in script
        assert str(pptx.resolve()) in script
        assert str(output.resolve()) in script
        prefix = output / "_keynote_export.png"
        _write_png_stub(prefix / "_keynote_export.png.001.png")
        _write_png_stub(prefix / "_keynote_export.png.002.png")
        return SimpleNamespace(stdout="2\n", stderr="", returncode=0)

    monkeypatch.setattr(render_template.subprocess, "run", fake_run)

    assert render_template._try_keynote_render(pptx, output) == 2
    assert sorted(path.name for path in output.glob("page-*.png")) == [
        "page-01.png",
        "page-02.png",
    ]
    assert not (output / "_keynote_export.png").exists()
