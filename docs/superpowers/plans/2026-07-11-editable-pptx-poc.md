# Editable PPTX Reconstruction POC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove in an isolated branch that a complete gpt-image-2 slide can retain its visual composition while known text becomes native PowerPoint text and overlapping visual layers follow the A1 → A2 → B policy.

**Architecture:** Keep the full generated slide as `visual_master`. Add a focused `scripts/editable_pptx/` package that calls an OpenAI-compatible Images API, composites edit results only inside explicit masks, extracts raster layers, renders native text and image layers into PPTX, and emits measurable evidence. The POC uses supplied boxes and masks so it tests visual feasibility before automatic OCR and segmentation.

**Tech Stack:** Python 3.12, OpenAI Python SDK, Pillow, python-pptx, pytest, existing Keynote renderer.

---

## Scope and merge gate

This POC does not implement automatic OCR, SAM/BiRefNet segmentation, automatic font search, or production CLI integration. Do not merge until:

1. All tracked regressions pass.
2. Provider generation and edit smokes pass against the configured endpoint.
3. Pixels outside the internal edit mask remain byte-identical.
4. The PPTX contains native text and independent pictures, not one full-slide raster.
5. Keynote renders the POC successfully.
6. The render has no visible old-text residue or text overflow.
7. A1 overlap extraction recomposes a fixture without visible seams.
8. `quality-report.json` records evidence and route decisions.

## File map

- Create `scripts/editable_pptx/provider.py`: SDK provider and b64 decoding.
- Create `scripts/editable_pptx/masking.py`: internal mask and pixel-locked compositing.
- Create `scripts/editable_pptx/layers.py`: A1 extraction and A1/A2/B routing.
- Create `scripts/editable_pptx/scene.py`: strict POC scene loader.
- Create `scripts/editable_pptx/renderer.py`: native text/image PPTX renderer.
- Create `scripts/editable_pptx/poc.py`: POC orchestration and quality report.
- Create `regression_tests/test_editable_*.py`: tracked POC tests.
- Create `examples/editable-pptx-poc/demo1-cover.scene.json`: real-slide annotation.
- Modify `requirements.txt`: add OpenAI SDK.

### Task 1: OpenAI-compatible image provider

**Files:**
- Create: `scripts/editable_pptx/__init__.py`
- Create: `scripts/editable_pptx/provider.py`
- Test: `regression_tests/test_editable_provider.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Write failing tests**

```python
def test_generate_writes_b64_png(tmp_path):
    client = FakeClient(generate_bytes=PNG_BYTES)
    provider = OpenAIImageProvider(client, "gpt-image-2", "high")
    output = provider.generate("完整 PPT 封面", tmp_path / "generated.png", "1024x1024")
    assert output.read_bytes() == PNG_BYTES
    assert client.generate_kwargs["model"] == "gpt-image-2"


def test_edit_sends_image_and_mask(tmp_path):
    image_path = write_png(tmp_path / "image.png")
    mask_path = write_png(tmp_path / "mask.png", mode="RGBA")
    client = FakeClient(edit_bytes=PNG_BYTES)
    provider = OpenAIImageProvider(client, "gpt-image-2", "high")
    output = provider.edit(image_path, mask_path, "只修复文字区域", tmp_path / "edited.png")
    assert output.read_bytes() == PNG_BYTES
    assert client.edit_kwargs["prompt"] == "只修复文字区域"
```

- [ ] **Step 2: Verify RED**

Run: `pytest -c /dev/null -o cache_dir=.pytest_cache regression_tests/test_editable_provider.py -q`

Expected: import fails because the package does not exist.

- [ ] **Step 3: Implement minimal provider**

Implement `OpenAIImageProvider.from_env()`, `generate()`, `edit()`, and `_decode_first_image()`. `from_env()` passes `OPENAI_BASE_URL` unchanged to `OpenAI(base_url=...)`, reads but never logs the key, and raises actionable errors for missing configuration or empty image data.

- [ ] **Step 4: Add dependency and verify GREEN**

Add `openai>=1.83,<2` to `requirements.txt`, then run:

```bash
pytest -c /dev/null -o cache_dir=.pytest_cache regression_tests/test_editable_provider.py -q
pytest -c /dev/null -o cache_dir=.pytest_cache regression_tests -q
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt scripts/editable_pptx regression_tests/test_editable_provider.py
git commit -m "feat: add OpenAI image provider adapter"
```

### Task 2: Mask semantics and pixel lock

**Files:**
- Create: `scripts/editable_pptx/masking.py`
- Test: `regression_tests/test_editable_masking.py`

- [ ] **Step 1: Write failing tests**

```python
def test_composite_changes_only_white_mask_pixels():
    original = solid_image((4, 4), (10, 20, 30))
    edited = solid_image((4, 4), (200, 210, 220))
    mask = black_mask((4, 4))
    mask.putpixel((2, 1), 255)
    result = composite_masked_edit(original, edited, mask)
    assert result.getpixel((2, 1)) == (200, 210, 220)
    assert result.getpixel((0, 0)) == (10, 20, 30)
    assert changed_outside_mask(original, result, mask) == 0


def test_api_mask_makes_replace_region_transparent():
    internal = black_mask((2, 2))
    internal.putpixel((1, 0), 255)
    api_mask = make_api_edit_mask(internal)
    assert api_mask.getpixel((1, 0))[3] == 0
    assert api_mask.getpixel((0, 0))[3] == 255
```

- [ ] **Step 2: Verify RED**

Run: `pytest -c /dev/null -o cache_dir=.pytest_cache regression_tests/test_editable_masking.py -q`

- [ ] **Step 3: Implement minimal functions**

Use the internal convention `0=preserve, 255=replace`. Implement RGBA API-mask conversion, exact compositing, and outside-mask changed-pixel counting. Never change pixels outside the caller mask.

- [ ] **Step 4: Verify and commit**

```bash
pytest -c /dev/null -o cache_dir=.pytest_cache regression_tests/test_editable_masking.py -q
pytest -c /dev/null -o cache_dir=.pytest_cache regression_tests -q
git add scripts/editable_pptx/masking.py regression_tests/test_editable_masking.py
git commit -m "feat: lock image edits to explicit masks"
```

### Task 3: A1 extraction and A1/A2/B routing

**Files:**
- Create: `scripts/editable_pptx/layers.py`
- Test: `regression_tests/test_editable_layers.py`

- [ ] **Step 1: Write failing tests**

```python
def test_a1_extract_preserves_visible_pixels():
    source, mask = overlapping_fixture()
    layer = extract_rgba_layer(source, mask)
    assert layer.getpixel((5, 5))[:3] == source.getpixel((5, 5))
    assert layer.getpixel((0, 0))[3] == 0


def test_route_order():
    assert choose_layer_strategy(LayerMetrics(.98, .01, .08), False) == "direct_extract"
    assert choose_layer_strategy(LayerMetrics(.95, .03, .42), False) == "occlusion_complete"
    assert choose_layer_strategy(LayerMetrics(.61, .24, .20), False) == "ai_regenerate"
    assert choose_layer_strategy(LayerMetrics(1, 0, 0), True) == "ai_regenerate"
```

- [ ] **Step 2: Verify RED**

Run: `pytest -c /dev/null -o cache_dir=.pytest_cache regression_tests/test_editable_layers.py -q`

- [ ] **Step 3: Implement minimal extraction and routing**

Implement `extract_rgba_layer`, `paste_layer`, `LayerMetrics`, `choose_layer_strategy`, and `build_ai_separation_prompt`. POC thresholds: A1 requires confidence `>=0.90`, edge contamination `<=0.08`, occlusion `<=0.20`; A2 handles qualifying masks above `0.20` occlusion; all other cases and design mode use B.

- [ ] **Step 4: Verify and commit**

```bash
pytest -c /dev/null -o cache_dir=.pytest_cache regression_tests/test_editable_layers.py -q
pytest -c /dev/null -o cache_dir=.pytest_cache regression_tests -q
git add scripts/editable_pptx/layers.py regression_tests/test_editable_layers.py
git commit -m "feat: add overlap layer routing"
```

### Task 4: EditableScene and native renderer

**Files:**
- Create: `scripts/editable_pptx/scene.py`
- Create: `scripts/editable_pptx/renderer.py`
- Test: `regression_tests/test_editable_renderer.py`

- [ ] **Step 1: Write failing renderer test**

```python
def test_renderer_creates_native_text_and_picture_layers(tmp_path):
    scene = EditableScene.from_dict(sample_scene(tmp_path))
    path = render_editable_pptx(scene, tmp_path / "editable.pptx")
    shapes = list(Presentation(path).slides[0].shapes)
    assert any(s.has_text_frame and s.text == "年度战略复盘" for s in shapes)
    assert any(s.shape_type == MSO_SHAPE_TYPE.PICTURE for s in shapes)
    assert len(shapes) >= 3
```

- [ ] **Step 2: Verify RED**

Run: `pytest -c /dev/null -o cache_dir=.pytest_cache regression_tests/test_editable_renderer.py -q`

- [ ] **Step 3: Implement strict scene parsing**

Accept one slide with `canvas`, `clean_plate`, `native_text`, and `image_layer` elements. Reject missing files, invalid bboxes, duplicate IDs, and unsupported types.

- [ ] **Step 4: Implement the renderer**

Create a 13.333 × 7.5 inch slide, add the clean plate first, then elements sorted by `z_index`. Map pixel bboxes to slide coordinates. Set font face, size, weight, color, alignment, margins, and object names. Keep image layers as independent pictures.

- [ ] **Step 5: Verify and commit**

```bash
pytest -c /dev/null -o cache_dir=.pytest_cache regression_tests/test_editable_renderer.py -q
pytest -c /dev/null -o cache_dir=.pytest_cache regression_tests -q
git add scripts/editable_pptx/scene.py scripts/editable_pptx/renderer.py regression_tests/test_editable_renderer.py
git commit -m "feat: render editable text and image layers"
```

### Task 5: Offline POC and quality report

**Files:**
- Create: `scripts/editable_pptx/poc.py`
- Create: `regression_tests/test_editable_poc.py`
- Create: `examples/editable-pptx-poc/demo1-cover.scene.json`

- [ ] **Step 1: Write failing end-to-end test**

```python
def test_offline_poc_emits_pptx_and_report(tmp_path):
    scene, edited = make_synthetic_poc(tmp_path)
    result = run_poc(scene, edited, tmp_path / "out")
    report = json.loads(result.report_path.read_text())
    assert result.pptx_path.exists()
    assert report["outside_mask_changed_pixels"] == 0
    assert report["native_text_count"] == 2
    assert report["status"] == "pass"
```

- [ ] **Step 2: Verify RED**

Run: `pytest -c /dev/null -o cache_dir=.pytest_cache regression_tests/test_editable_poc.py -q`

- [ ] **Step 3: Implement orchestration**

Load a scene, build a pixel-locked clean plate from an edited candidate, render native objects, inspect the PPTX, and write `quality-report.json`. Pass only when outside-mask changes are zero and every declared text element exists natively.

- [ ] **Step 4: Add real cover annotation**

Annotate `docs/assets/demo1_after.jpg` with title `年度战略复盘`, subtitle `AI 驱动的数字化未来`, pixel bboxes, font candidates, colors, and a combined repair mask definition.

- [ ] **Step 5: Verify and commit**

```bash
pytest -c /dev/null -o cache_dir=.pytest_cache regression_tests/test_editable_poc.py -q
pytest -c /dev/null -o cache_dir=.pytest_cache regression_tests -q
git add scripts/editable_pptx/poc.py regression_tests/test_editable_poc.py examples/editable-pptx-poc
git commit -m "feat: add editable pptx effect POC"
```

### Task 6: Live API and Keynote validation

**Files:** Runtime output only under `outputs/editable-pptx-poc/`.

- [ ] **Step 1: Confirm secure configuration**

Confirm an ignored local `.env` contains a newly rotated key plus `OPENAI_BASE_URL=https://api.krill-ai.com/v1`, `GPT_IMAGE_MODEL_NAME=gpt-image-2`, and `GPT_IMAGE_QUALITY=high`. Never print the key.

- [ ] **Step 2: Run generation and edit smokes**

Generate one test image. Then edit `demo1_after.jpg` through the combined title/subtitle mask with a prompt that reconstructs only the dark neon background and adds no text or new objects. Record response type, dimensions, and duration.

- [ ] **Step 3: Build and render**

Build `editable.pptx`, then run:

```bash
python3 scripts/render_template.py outputs/editable-pptx-poc/editable.pptx \
  -o outputs/editable-pptx-poc/rendered --force
```

Expected: one page and a render manifest with `page_count: 1`.

- [ ] **Step 4: Apply the merge gate**

Inspect the visual master, clean plate, PPTX render, and quality report. Do not merge if old text remains, the neon background is damaged, native text overflows, outside-mask pixels change, or tracked tests fail.

- [ ] **Step 5: Fix only through TDD**

Any live defect must first be reproduced by a failing tracked regression test. Do not commit `.env` or runtime outputs.
