from pathlib import Path


def test_readme_documents_default_off_editable_example():
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "默认关闭" in readme
    assert "帮我生成一份可编辑模式的 PPT" in readme
    assert "CLI 仅在明确要求时开启" not in readme
    assert "python3 scripts/" not in readme
    assert "examples/editable-pptx/case05-summer-poster/original.png" in readme
    assert "examples/editable-pptx/case05-summer-poster/rendered.png" in readme
    assert "examples/editable-pptx/case05-summer-poster/editable.pptx" in readme
    assert "13 个可选对象" in readme
    assert "5 个原生文本" in readme
    assert "6 个原生 shape" in readme


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
    assert "create this deck in editable mode" in english.lower()
    assert "--editable --editable-scenes" not in english
    assert "python3 scripts/" not in english
    assert "case05-summer-poster/editable.pptx" in english
    assert "13 selectable objects" in english
    assert "5 native text boxes" in english
    assert "6 native shapes" in english


def test_case05_readme_is_a_complete_visual_case_study():
    case = Path("examples/editable-pptx/case05-summer-poster/README.md").read_text(
        encoding="utf-8"
    )
    for path in (
        "./original.png",
        "./rendered.png",
        "./clean-plate.png",
        "./layers/mascot-icecream-group.png",
        "./edge-check-white.png",
        "./edge-check-black.png",
        "./editable.pptx",
        "./slide-01.scene.json",
        "./quality-report.json",
    ):
        assert path in case
    assert "13 个可选对象" in case
    assert "A1" in case and "A2" in case and "B" in case
    assert "python3" not in case


def test_local_process_docs_are_ignored_without_hiding_authoritative_docs():
    gitignore = Path(".gitignore").read_text(encoding="utf-8").splitlines()
    assert "/docs/reddit-launch-copy.md" in gitignore
    assert "/docs/superpowers/" in gitignore
    assert not any("external_image_overlay_logic.txt" in line for line in gitignore)


def test_readme_follows_demo_quickstart_capabilities_advanced_order():
    readme = Path("README.md").read_text(encoding="utf-8")
    headings = (
        "## 🎬 效果演示",
        "## 🧩 可编辑模式示例",
        "## 🚀 快速开始",
        "## ✨ 能做什么",
        "## ✅ 适合哪些用户场景",
        "## 🛠 手动安装与高级配置",
        "## 📚 技术文档",
        "## 🆕 更新记录",
    )
    positions = [readme.index(heading) for heading in headings]
    assert positions == sorted(positions)
    assert "在 Claude Code 里怎么用" not in readme
    assert "普通生成" in readme and "仿模板" in readme and "可编辑交付" in readme

    english = Path("docs/README.en.md").read_text(encoding="utf-8")
    english_headings = (
        "## 🎬 Demo",
        "## 🧩 Opt-in editable mode example",
        "## 🚀 Quick start",
        "## ✨ What it does",
        "## ✅ Best-fit use cases",
        "## 🛠 Manual install and advanced configuration",
        "## 📚 Technical documentation",
        "## 🆕 Changelog",
    )
    english_positions = [english.index(heading) for heading in english_headings]
    assert english_positions == sorted(english_positions)
    assert "How to use inside Claude Code" not in english
