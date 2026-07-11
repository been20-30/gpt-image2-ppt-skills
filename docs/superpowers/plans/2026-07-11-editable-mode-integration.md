# Opt-in Editable Mode Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in `--editable` path that converts validated scene manifests into genuinely editable PPTX files while leaving the default image-based workflow unchanged.

**Architecture:** Extend `scripts/editable_pptx/` into a reusable schema, native-object renderer, and multi-slide workflow. `generate_ppt.py` always keeps the normal PPTX path; only `--editable` builds `<title>-editable.pptx`. Agent rules in `SKILL.md` govern scene preparation, A1 → A2 → B routing, evidence, and visual review.

**Tech Stack:** Python 3.8+, Pillow, python-pptx, pytest, existing image provider and Office renderer.

---

## File map

- Modify `scripts/editable_pptx/scene.py`: text, image, native shape, connector schema.
- Modify `scripts/editable_pptx/renderer.py`: all element types and multi-slide decks.
- Create `scripts/editable_pptx/workflow.py`: scene discovery, deck build, quality summary.
- Modify `scripts/editable_pptx/__init__.py`: public entry points.
- Modify `scripts/generate_ppt.py`: default-off CLI integration.
- Add `regression_tests/test_editable_{scene_shapes,deck,workflow,cli,example,docs}.py`.
- Add `examples/editable-pptx/case05-summer-poster/` with approved artifacts.
- Modify `README.md`, `SKILL.md`, `AGENTS.md`, `docs/README.en.md`.

### Task 1: Extend the scene schema

**Files:**
- Modify: `scripts/editable_pptx/scene.py`
- Create: `regression_tests/test_editable_scene_shapes.py`

- [ ] **Step 1: Write failing tests**

Test a scene containing:

```python
{
  "id": "banner", "type": "native_shape",
  "bbox_px": [100, 100, 500, 120], "z_index": 10,
  "style": {"shape": "rounded_rectangle", "fill": "#FFF4C2", "line": "#E8B932"}
}
{
  "id": "flow", "type": "connector",
  "bbox_px": [600, 160, 300, 0], "z_index": 11,
  "style": {"line": "#7752C8", "line_width_pt": 2, "end_arrow": True}
}
```

Also assert rejection of duplicate IDs, unknown shape names, invalid hex colors, and connectors whose width and height are both zero.

- [ ] **Step 2: Verify RED**

```bash
pytest --rootdir=. -c /dev/null -o cache_dir=.pytest_cache regression_tests/test_editable_scene_shapes.py -q
```

Expected: unsupported element type failure.

- [ ] **Step 3: Implement minimal schema support**

Use:

```python
SUPPORTED_TYPES = {"native_text", "image_layer", "native_shape", "connector"}
SUPPORTED_SHAPES = {"rectangle", "rounded_rectangle", "ellipse", "star_5", "line"}
```

Add strict color, shape, bbox, connector, and asset validation. Permit one connector dimension to be zero.

- [ ] **Step 4: Verify GREEN**

```bash
pytest --rootdir=. -c /dev/null -o cache_dir=.pytest_cache \
  regression_tests/test_editable_scene_shapes.py regression_tests/test_editable_renderer.py -q
```

- [ ] **Step 5: Commit**

```bash
git add scripts/editable_pptx/scene.py regression_tests/test_editable_scene_shapes.py
git commit -m "feat: support editable shapes and connectors"
```

### Task 2: Render shapes, connectors, and multiple slides

**Files:**
- Modify: `scripts/editable_pptx/renderer.py`
- Create: `regression_tests/test_editable_deck.py`

- [ ] **Step 1: Write a failing two-slide test**

Build two scenes. Slide 1 has text, a rounded rectangle, and a star. Slide 2 has an image layer and arrow connector. Assert two slides, expected object names, correct z-order, and native PowerPoint shape types.

- [ ] **Step 2: Verify RED**

```bash
pytest --rootdir=. -c /dev/null -o cache_dir=.pytest_cache regression_tests/test_editable_deck.py -q
```

Expected: `render_editable_deck` import failure.

- [ ] **Step 3: Implement reusable rendering**

Add:

```python
def add_editable_slide(prs, scene): ...
def render_editable_deck(scenes, output_path): ...
def render_editable_pptx(scene, output_path):
    return render_editable_deck([scene], output_path)
```

Map supported shape names to `MSO_AUTO_SHAPE_TYPE`, apply fill/line transparency, rotation and object names, and render straight connectors with optional arrowheads.

- [ ] **Step 4: Verify GREEN and commit**

```bash
pytest --rootdir=. -c /dev/null -o cache_dir=.pytest_cache \
  regression_tests/test_editable_deck.py regression_tests/test_editable_renderer.py -q
git add scripts/editable_pptx/renderer.py regression_tests/test_editable_deck.py
git commit -m "feat: render multi-slide editable decks"
```

### Task 3: Add scene-directory workflow and reports

**Files:**
- Create: `scripts/editable_pptx/workflow.py`
- Modify: `scripts/editable_pptx/__init__.py`
- Create: `regression_tests/test_editable_workflow.py`

- [ ] **Step 1: Write failing tests**

Required behaviors:

```python
with pytest.raises(ValueError, match="slide-02.scene.json"):
    discover_scene_files(scene_dir_with_only_slide_1, [1, 2])

result = build_editable_output(two_scene_dir, [2, 1], output_dir, "季度复盘")
assert result.pptx_path.name == "季度复盘-editable.pptx"
assert json.loads(result.report_path.read_text())["mode"] == "editable"
```

Also test relative asset resolution, duplicate scene slide numbers, object counts, and empty scene directories.

- [ ] **Step 2: Verify RED**

```bash
pytest --rootdir=. -c /dev/null -o cache_dir=.pytest_cache regression_tests/test_editable_workflow.py -q
```

- [ ] **Step 3: Implement workflow**

Provide:

```python
@dataclass(frozen=True)
class EditableBuildResult:
    pptx_path: Path
    report_path: Path
    scene_files: tuple[Path, ...]

def discover_scene_files(scene_dir, slide_numbers): ...
def load_scene_file(path): ...
def inventory_scenes(scenes): ...
def build_editable_output(scene_dir, slide_numbers, output_dir, title): ...
```

Resolve scene paths relative to each JSON file. Write `editable-quality-report.json` with slide count, per-type counts, scene list, final PPTX and status.

- [ ] **Step 4: Export API, verify, and commit**

```bash
pytest --rootdir=. -c /dev/null -o cache_dir=.pytest_cache regression_tests/test_editable_workflow.py -q
git add scripts/editable_pptx/workflow.py scripts/editable_pptx/__init__.py regression_tests/test_editable_workflow.py
git commit -m "feat: build editable decks from scene directories"
```

### Task 4: Integrate the default-off CLI mode

**Files:**
- Modify: `scripts/generate_ppt.py`
- Create: `regression_tests/test_editable_cli.py`

- [ ] **Step 1: Write failing parser and resolver tests**

```python
args = create_argument_parser().parse_args([])
assert args.editable is False
assert args.editable_scenes is None

args = create_argument_parser().parse_args(["--editable", "--editable-scenes", "scenes"])
assert args.editable is True
```

Test `resolve_editable_scene_dir(args, output_dir)` for explicit path, `<output_dir>/editable_scenes` fallback, missing-directory failure, and no filesystem access when editable is false.

- [ ] **Step 2: Verify RED**

```bash
pytest --rootdir=. -c /dev/null -o cache_dir=.pytest_cache regression_tests/test_editable_cli.py -q
```

- [ ] **Step 3: Add flags and integration**

Add:

```python
parser.add_argument("--editable", action="store_true", help="生成可编辑对象版 PPTX；默认关闭")
parser.add_argument("--editable-scenes", help="slide-XX.scene.json 所在目录；仅与 --editable 一起使用")
```

Reject `--editable-scenes` without `--editable`. Keep the existing `generate_pptx(...)` call unchanged. Afterwards, if editable mode is on, call `build_editable_output(...)`, retain both outputs, and print both paths. A missing scene must exit non-zero without deleting the normal PPTX.

- [ ] **Step 4: Verify default behavior and commit**

```bash
pytest --rootdir=. -c /dev/null -o cache_dir=.pytest_cache regression_tests/test_editable_cli.py -q
pytest --rootdir=. -c /dev/null -o cache_dir=.pytest_cache regression_tests -q
git add scripts/generate_ppt.py regression_tests/test_editable_cli.py
git commit -m "feat: add opt-in editable generation mode"
```

### Task 5: Promote approved Case 05 into the repository

**Files:**
- Create: `examples/editable-pptx/case05-summer-poster/original.png`
- Create: `examples/editable-pptx/case05-summer-poster/clean-plate.png`
- Create: `examples/editable-pptx/case05-summer-poster/layers/mascot-icecream-group.png`
- Create: `examples/editable-pptx/case05-summer-poster/edge-check-{white,black}.png`
- Create: `examples/editable-pptx/case05-summer-poster/slide-01.scene.json`
- Create: `examples/editable-pptx/case05-summer-poster/editable.pptx`
- Create: `examples/editable-pptx/case05-summer-poster/rendered.png`
- Create: `examples/editable-pptx/case05-summer-poster/quality-report.json`
- Create: `examples/editable-pptx/case05-summer-poster/README.md`
- Create: `regression_tests/test_editable_example.py`

- [ ] **Step 1: Write a failing example contract test**

Assert that all files exist, scene paths resolve, the PPTX opens, and object names include `clean_plate`, `main_title`, `product_line`, and `mascot_icecream_group`. Assert the group is a picture and title/product line are native text.

- [ ] **Step 2: Verify RED**

```bash
pytest --rootdir=. -c /dev/null -o cache_dir=.pytest_cache regression_tests/test_editable_example.py -q
```

- [ ] **Step 3: Copy only approved finals and create relative scene JSON**

Copy original, clean plate, cropped transparent layer, black/white edge checks and approved render from the isolated Case 05 output. Do not copy `.env`, raw API results, chroma intermediates or rejected attempts. The scene contains five native text elements, the editable panel/banner/badge/stars as native shapes, and the independent image layer.

- [ ] **Step 4: Build with production workflow**

```bash
PYTHONPATH=. python3 -c "from scripts.editable_pptx.workflow import build_editable_output; build_editable_output('examples/editable-pptx/case05-summer-poster', [1], 'examples/editable-pptx/case05-summer-poster', '夏日星星人')"
python3 scripts/render_template.py examples/editable-pptx/case05-summer-poster/夏日星星人-editable.pptx \
  -o /tmp/case05-example-render --force
```

Copy the approved workflow deck to `editable.pptx` and page PNG to `rendered.png`.

- [ ] **Step 5: Inspect and commit**

Inspect original, render, both edge checks and deck object list. Then:

```bash
pytest --rootdir=. -c /dev/null -o cache_dir=.pytest_cache regression_tests/test_editable_example.py -q
git add examples/editable-pptx regression_tests/test_editable_example.py
git commit -m "docs: add editable summer poster example"
```

### Task 6: Update README and skill instructions

**Files:**
- Modify: `README.md`
- Modify: `SKILL.md`
- Modify: `AGENTS.md`
- Modify: `docs/README.en.md`
- Create: `regression_tests/test_editable_docs.py`

- [ ] **Step 1: Write failing documentation contract tests**

Assert README contains `--editable`, “默认关闭”, Case 05 original/render/PPTX links; SKILL contains A1/A2/B, `native_shape`, `connector`, scene/output rules; AGENTS points to the authoritative editable section.

- [ ] **Step 2: Verify RED**

```bash
pytest --rootdir=. -c /dev/null -o cache_dir=.pytest_cache regression_tests/test_editable_docs.py -q
```

- [ ] **Step 3: Update README**

Add editable mode to the capability list and update record. Add a two-column original/rendered Case 05 table and a download link to `editable.pptx`. State the mode is default-off and complex visuals may remain independent image layers.

- [ ] **Step 4: Update SKILL.md**

Add the authoritative “可编辑模式（默认关闭）” workflow: trigger phrases, CLI, scenes, four element types, A1 → A2 → B, overlap grouping default, clean plate, mask lock, edge checks, move test, Office render, architecture-diagram rule, no silent fallback, outputs and delivery paths.

- [ ] **Step 5: Update thin indexes, verify, and commit**

Keep AGENTS thin. Add a concise English announcement and example links. Then:

```bash
pytest --rootdir=. -c /dev/null -o cache_dir=.pytest_cache regression_tests/test_editable_docs.py -q
git diff --check
git add README.md SKILL.md AGENTS.md docs/README.en.md regression_tests/test_editable_docs.py
git commit -m "docs: document opt-in editable mode"
```

### Task 7: Full verification and merge readiness

**Files:** Review all changed files and committed example artifacts.

- [ ] **Step 1: Run all tracked regressions**

```bash
pytest --rootdir=. -c /dev/null -o cache_dir=.pytest_cache regression_tests -q
```

- [ ] **Step 2: Run default-off and editable CLI smokes**

Use existing one-slide images to avoid API calls. Without `--editable`, confirm no scene lookup and only normal packaging. With `--editable --editable-scenes examples/editable-pptx/case05-summer-poster`, confirm both normal and editable PPTX paths.

- [ ] **Step 3: Render and inspect Case 05**

```bash
python3 scripts/render_template.py examples/editable-pptx/case05-summer-poster/editable.pptx \
  -o /tmp/case05-final-render --force
```

Compare `/tmp/case05-final-render/page-01.png` with committed `rendered.png`; inspect text, matte edge and object duplication.

- [ ] **Step 4: Check repository hygiene**

```bash
git diff --check
git status --short
git ls-files | rg '(^|/)\.env$|api-edited-raw|subject-chroma-raw'
```

Expected: no credentials, raw API responses, rejected attempts or runtime output directories are tracked.

- [ ] **Step 5: Finish safely**

Use `verification-before-completion`, `requesting-code-review`, then `finishing-a-development-branch`. Do not merge until tests pass and the committed Case 05 original/render/PPTX example is approved.
