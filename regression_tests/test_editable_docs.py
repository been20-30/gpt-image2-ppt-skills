from pathlib import Path


def test_readme_documents_default_off_editable_example():
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "--editable" in readme
    assert "默认关闭" in readme
    assert "examples/editable-pptx/case05-summer-poster/original.png" in readme
    assert "examples/editable-pptx/case05-summer-poster/rendered.png" in readme
    assert "examples/editable-pptx/case05-summer-poster/editable.pptx" in readme


def test_skill_contains_authoritative_editable_workflow():
    skill = Path("SKILL.md").read_text(encoding="utf-8")
    assert "## 可编辑模式（默认关闭）" in skill
    assert "--editable-scenes" in skill
    assert "A1" in skill and "A2" in skill and "B" in skill
    assert "native_shape" in skill
    assert "connector" in skill
    assert "不得静默" in skill


def test_thin_agent_index_and_english_readme_link_editable_mode():
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    english = Path("docs/README.en.md").read_text(encoding="utf-8")
    assert "可编辑模式" in agents
    assert "opt-in editable" in english.lower()
    assert "case05-summer-poster/editable.pptx" in english
