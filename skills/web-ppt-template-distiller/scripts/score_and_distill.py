#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import re
import sqlite3
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any


DEFAULT_STYLES_DIR = Path(".ppt-template-distill/staged_styles")
DEFAULT_WORK_DIR = Path(".ppt-template-distill/provenance")
DEFAULT_STATE_DB = Path(".ppt-template-distill/distill_state.sqlite")
USER_AGENT = "web-ppt-template-distiller/0.1"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_ROOT.parent.parent
DEFAULT_VALIDATION_ROLES = ("cover", "section", "content", "data")
GENERALIZATION_VALIDATION_CASES = (
    "cover",
    "section",
    "content",
    "data",
    "comparison",
    "data-table-timeline",
)
VALIDATION_SCENARIOS: dict[str, dict[str, str]] = {
    "cover": {
        "title": "Quarterly Strategy Review",
        "purpose": "Test first-impression identity, title hierarchy, palette, whitespace, and signature decoration.",
        "content": "Title: Quarterly Strategy Review. Subtitle: Building durable growth through focus and execution. Small label: Executive Briefing / 2026.",
    },
    "section": {
        "title": "02 / Growth Engine",
        "purpose": "Test whether the style can create a rhythmic section break without copying a source composition.",
        "content": "Section number: 02. Section title: Growth Engine. Supporting line: Turning strategic choices into repeatable momentum.",
    },
    "content": {
        "title": "Three Operating Priorities",
        "purpose": "Test medium-density hierarchy, reusable grid behavior, and body-text legibility.",
        "content": "Heading: Three Operating Priorities. Items: Focus the portfolio — concentrate resources on the highest-conviction opportunities. Shorten the learning loop — turn customer evidence into weekly decisions. Scale what works — standardize repeatable practices without losing local judgment.",
    },
    "data": {
        "title": "Momentum at a Glance",
        "purpose": "Test numeric hierarchy, chart language, labeling, and high-density transfer.",
        "content": "Heading: Momentum at a Glance. Metrics: Revenue +24%, Retention 91%, Cycle time -18%. Quarterly values 62, 71, 79, 88 for Q1, Q2, Q3, Q4 respectively. Use the chart or data structure required by the compiled layout directive; if the directive is silent, choose one restrained chart. Use clear labels and no decorative fake data.",
    },
    "comparison": {
        "title": "From Fragmented to Focused",
        "purpose": "Test paired structure, contrast, and semantic separation.",
        "content": "Heading: From Fragmented to Focused. Before: scattered priorities, slow feedback, duplicated effort. After: clear bets, weekly evidence, shared operating system.",
        "page_type": "content",
        "semantic_role": "comparison",
    },
    "data-table-timeline": {
        "title": "Operating Model Readiness",
        "purpose": "Hold out a mixed table-and-timeline shape to detect validation-sample overfitting and verify production routing.",
        "content": "Heading: Operating Model Readiness. Table: Capability | Current | Target. Governance | Fragmented | Unified. Handoffs | Manual | Automated. Timeline: 2026 Q1 Diagnose; 2026 Q2 Pilot; 2026 Q3 Scale; 2026 Q4 Standardize.",
        "page_type": "data",
        "semantic_role": "data",
    },
    "closing": {
        "title": "Make the Next Move Count",
        "purpose": "Test whether the visual identity remains recognizable in a restrained closing slide.",
        "content": "Closing statement: Make the Next Move Count. Supporting line: Align the team, commit the resources, and begin the first learning cycle.",
    },
}
ENV_KEYS = {
    "OPENAI_BASE_URL",
    "OPENAI_API_KEY",
    "GPT_IMAGE_MODEL_NAME",
    "GPT_IMAGE_QUALITY",
    "GPT_IMAGE_ENDPOINT",
    "VISION_BASE_URL",
    "VISION_API_KEY",
    "VISION_MODEL_NAME",
}


@dataclass(frozen=True)
class ImageCandidate:
    url: str
    slide_index: int
    width: int
    height: int
    source: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_scoped_env_files() -> list[str]:
    candidates: list[Path] = []
    explicit = os.environ.get("GPT_IMAGE2_PPT_ENV")
    if explicit:
        candidates.append(Path(explicit).expanduser())
    candidates.extend(
        [
            REPO_ROOT / ".env",
            Path.home() / ".codex/skills/gpt-image2-ppt-skills/.env",
            Path.home() / ".claude/skills/gpt-image2-ppt-skills/.env",
        ]
    )
    loaded: list[str] = []
    seen: set[str] = set()
    for path in candidates:
        if not path.is_file():
            continue
        resolved = str(path.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key in ENV_KEYS and value and not os.environ.get(key):
                os.environ[key] = value
        loaded.append(resolved)
    return loaded


def manifest_source_hash(manifest: dict[str, Any]) -> str:
    payload = {
        "source_pages": manifest.get("source_pages", []),
        "images": [
            {
                "url": item.get("url"),
                "slide_index": item.get("slide_index"),
                "width": item.get("width"),
                "height": item.get("height"),
            }
            for item in manifest.get("images", [])
        ],
    }
    return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            create table if not exists templates (
                canonical_url text primary key,
                url_key text not null,
                style_id text,
                style_name text,
                title text,
                description text,
                status text not null,
                total_score real,
                decision text,
                source_hash text,
                work_dir text,
                manifest_path text,
                quality_report_path text,
                distill_prompt_path text,
                style_profile_path text,
                validation_report_path text,
                validation_image_path text,
                output_style_path text,
                error text,
                first_seen_at text not null,
                updated_at text not null
            );
            create table if not exists images (
                image_url text primary key,
                canonical_url text not null,
                slide_index integer,
                width integer,
                height integer,
                local_path text,
                content_hash text,
                downloaded_at text,
                foreign key(canonical_url) references templates(canonical_url)
            );
            create table if not exists runs (
                run_id text primary key,
                started_at text not null,
                finished_at text,
                status text not null,
                args_json text,
                error text
            );
            """
        )
        existing_cols = {
            row["name"]
            for row in self.conn.execute("pragma table_info(templates)").fetchall()
        }
        for col in ["style_profile_path", "validation_report_path", "validation_image_path"]:
            if col not in existing_cols:
                self.conn.execute(f"alter table templates add column {col} text")
        self.conn.commit()

    def begin_run(self, args: argparse.Namespace) -> str:
        run_id = sha256_text(f"{utc_now()}:{json.dumps(vars(args), sort_keys=True, default=str)}")[:16]
        self.conn.execute(
            "insert into runs(run_id, started_at, status, args_json) values (?, ?, ?, ?)",
            (run_id, utc_now(), "running", json.dumps(vars(args), ensure_ascii=False, default=str)),
        )
        self.conn.commit()
        return run_id

    def finish_run(self, run_id: str, status: str, error: str = "") -> None:
        self.conn.execute(
            "update runs set finished_at = ?, status = ?, error = ? where run_id = ?",
            (utc_now(), status, error, run_id),
        )
        self.conn.commit()

    def get(self, canonical_url: str) -> sqlite3.Row | None:
        cur = self.conn.execute("select * from templates where canonical_url = ?", (canonical_url,))
        return cur.fetchone()

    def upsert_template(self, manifest: dict[str, Any], status: str, work_dir: Path) -> None:
        canonical_url = manifest.get("canonical_url") or manifest.get("source_pages", [{}])[0].get("canonical_url")
        now = utc_now()
        self.conn.execute(
            """
            insert into templates(
                canonical_url, url_key, style_id, style_name, title, description, status,
                work_dir, manifest_path, first_seen_at, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(canonical_url) do update set
                style_id=excluded.style_id,
                style_name=excluded.style_name,
                title=excluded.title,
                description=excluded.description,
                status=excluded.status,
                work_dir=excluded.work_dir,
                manifest_path=excluded.manifest_path,
                updated_at=excluded.updated_at,
                error=''
            """,
            (
                canonical_url,
                sha256_text(canonical_url)[:16],
                manifest.get("style_id"),
                manifest.get("style_name"),
                manifest.get("title"),
                manifest.get("description"),
                status,
                str(work_dir),
                str(work_dir / "source_manifest.json"),
                now,
                now,
            ),
        )
        self.conn.commit()

    def update_quality(self, canonical_url: str, quality: dict[str, Any], quality_path: Path, source_hash: str) -> None:
        self.conn.execute(
            """
            update templates
            set status = ?, total_score = ?, decision = ?, source_hash = ?,
                quality_report_path = ?, updated_at = ?, error = ''
            where canonical_url = ?
            """,
            (
                "scored",
                quality.get("total_score"),
                quality.get("decision"),
                source_hash,
                str(quality_path),
                utc_now(),
                canonical_url,
            ),
        )
        self.conn.commit()

    def update_status(self, canonical_url: str, status: str, **paths: str) -> None:
        allowed = {
            "distill_prompt_path",
            "style_profile_path",
            "validation_report_path",
            "validation_image_path",
            "output_style_path",
            "error",
        }
        assignments = ["status = ?", "updated_at = ?"]
        values: list[Any] = [status, utc_now()]
        for key, value in paths.items():
            if key not in allowed:
                continue
            assignments.append(f"{key} = ?")
            values.append(value)
        values.append(canonical_url)
        self.conn.execute(f"update templates set {', '.join(assignments)} where canonical_url = ?", values)
        self.conn.commit()

    def record_images(self, canonical_url: str, image_records: list[dict[str, Any]]) -> None:
        for item in image_records:
            local_path = Path(item["path"])
            content_hash = sha256_file(local_path) if local_path.exists() else ""
            self.conn.execute(
                """
                insert into images(image_url, canonical_url, slide_index, width, height, local_path, content_hash, downloaded_at)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(image_url) do update set
                    canonical_url=excluded.canonical_url,
                    slide_index=excluded.slide_index,
                    width=excluded.width,
                    height=excluded.height,
                    local_path=excluded.local_path,
                    content_hash=excluded.content_hash,
                    downloaded_at=excluded.downloaded_at
                """,
                (
                    item.get("url"),
                    canonical_url,
                    item.get("slide_index"),
                    item.get("width"),
                    item.get("height"),
                    item.get("path"),
                    content_hash,
                    utc_now(),
                ),
            )
        self.conn.commit()

    def list_templates(self) -> list[sqlite3.Row]:
        cur = self.conn.execute(
            """
            select updated_at, status, decision, total_score, style_id, title, canonical_url,
                   output_style_path, distill_prompt_path, error
            from templates
            order by updated_at desc
            """
        )
        return list(cur.fetchall())


def fetch_bytes(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_text(url: str, timeout: int = 30) -> str:
    return fetch_bytes(url, timeout=timeout).decode("utf-8", errors="replace")


def clean_text(value: str) -> str:
    value = unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def slugify(value: str, fallback: str = "web-ppt-style") -> str:
    value = unescape(value).lower()
    value = re.sub(r"https?://", "", value)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or fallback


def absolute_url(url: str, base_url: str) -> str:
    return urllib.parse.urljoin(base_url, unescape(url).strip())


def extract_meta(html: str, url: str) -> dict[str, str]:
    def first(patterns: list[str]) -> str:
        for pattern in patterns:
            match = re.search(pattern, html, flags=re.I | re.S)
            if match:
                return clean_text(match.group(1))
        return ""

    title = first(
        [
            r"<title[^>]*>(.*?)</title>",
            r'<meta\s+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        ]
    )
    description = first(
        [
            r'<meta\s+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta\s+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        ]
    )
    canonical = first([r'<link\s+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']']) or url
    return {
        "title": title,
        "description": description,
        "canonical_url": canonical,
        "page_slug": slugify(Path(urllib.parse.urlparse(canonical).path).name or title),
    }


def parse_srcset(srcset: str, base_url: str) -> list[tuple[str, int]]:
    items: list[tuple[str, int]] = []
    for part in unescape(srcset).split(","):
        tokens = part.strip().split()
        if not tokens:
            continue
        width = 0
        if len(tokens) > 1 and tokens[1].endswith("w"):
            try:
                width = int(tokens[1][:-1])
            except ValueError:
                width = 0
        items.append((absolute_url(tokens[0], base_url), width))
    return items


def infer_dimensions(url: str, width_hint: int = 0) -> tuple[int, int]:
    match = re.search(r"_(\d{3,5})_(\d{3,5})\.(?:jpe?g|png|webp)(?:\?|$)", url, flags=re.I)
    if match:
        return int(match.group(1)), int(match.group(2))
    return width_hint, 0


def infer_slide_index(url: str, fallback: int) -> int:
    name = Path(urllib.parse.urlparse(url).path).name
    match = re.match(r"(\d+)[-_]", name)
    return int(match.group(1)) if match else fallback


def extract_image_candidates(html: str, base_url: str) -> list[ImageCandidate]:
    candidates: list[ImageCandidate] = []
    seen: set[str] = set()
    fallback = 0

    for match in re.finditer(r'\b(?:srcset|imagesrcset)=["\']([^"\']+)["\']', html, flags=re.I | re.S):
        for image_url, width_hint in parse_srcset(match.group(1), base_url):
            path = urllib.parse.urlparse(image_url).path.lower()
            if Path(path).suffix not in IMAGE_EXTS or image_url in seen:
                continue
            if "responsive-images" not in path and "media" not in image_url:
                continue
            seen.add(image_url)
            width, height = infer_dimensions(image_url, width_hint)
            candidates.append(ImageCandidate(image_url, infer_slide_index(image_url, fallback), width, height, "srcset"))
            fallback += 1

    for match in re.finditer(
        r'\b(?:src|href|content)=["\']([^"\']+\.(?:jpe?g|png|webp)(?:\?[^"\']*)?)["\']',
        html,
        flags=re.I | re.S,
    ):
        image_url = absolute_url(match.group(1), base_url)
        path = urllib.parse.urlparse(image_url).path.lower()
        if Path(path).suffix not in IMAGE_EXTS or image_url in seen:
            continue
        seen.add(image_url)
        width, height = infer_dimensions(image_url)
        candidates.append(ImageCandidate(image_url, infer_slide_index(image_url, fallback), width, height, "image"))
        fallback += 1

    return candidates


def select_preview_images(candidates: list[ImageCandidate], max_images: int, preferred_width: int) -> list[ImageCandidate]:
    by_slide: dict[int, list[ImageCandidate]] = {}
    for item in candidates:
        path = urllib.parse.urlparse(item.url).path.lower()
        if "logo" in path or "favicon" in path:
            continue
        by_slide.setdefault(item.slide_index, []).append(item)

    selected: list[ImageCandidate] = []
    for slide_index in sorted(by_slide):
        pool = by_slide[slide_index]
        responsive = [item for item in pool if "responsive-images" in item.url]
        pool = responsive or pool
        under = [item for item in pool if item.width and item.width <= preferred_width]
        best = max(under, key=lambda item: (item.width, item.height)) if under else max(pool, key=lambda item: item.width)
        selected.append(best)
        if len(selected) >= max_images:
            break
    return selected


def download_images(images: list[ImageCandidate], output_dir: Path, delay: float) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for i, image in enumerate(images, start=1):
        suffix = Path(urllib.parse.urlparse(image.url).path).suffix.lower() or ".jpg"
        target = output_dir / f"{i:02d}_slide_{image.slide_index:02d}{suffix}"
        if not target.exists():
            target.write_bytes(fetch_bytes(image.url))
            time.sleep(delay)
        content_hash = sha256_file(target) if target.exists() else ""
        records.append(
            {
                "path": str(target),
                "url": image.url,
                "slide_index": image.slide_index,
                "width": image.width,
                "height": image.height,
                "content_hash": content_hash,
                "source": image.source,
            }
        )
    return records


def safe_open_image(path: Path):
    from PIL import Image

    image = Image.open(path).convert("RGB")
    image.thumbnail((192, 108))
    return image


def image_features(path: Path) -> dict[str, Any]:
    try:
        image = safe_open_image(path)
    except Exception:
        return {"ok": False}

    pixels = list(image.getdata())
    count = max(len(pixels), 1)
    means = [sum(pixel[i] for pixel in pixels) / count for i in range(3)]
    lumas = [(0.299 * r + 0.587 * g + 0.114 * b) for r, g, b in pixels]
    luma_std = statistics.pstdev(lumas) if len(lumas) > 1 else 0
    dark = sum(1 for v in lumas if v < 45) / count
    light = sum(1 for v in lumas if v > 235) / count
    quantized = image.quantize(colors=8).convert("RGB")
    colors = quantized.getcolors(maxcolors=256) or []
    palette = []
    for amount, color in sorted(colors, reverse=True)[:8]:
        r, g, b = color
        if amount / count < 0.015:
            continue
        palette.append(f"#{r:02X}{g:02X}{b:02X}")
    return {
        "ok": True,
        "mean": means,
        "luma_std": luma_std,
        "dark_ratio": dark,
        "light_ratio": light,
        "palette": palette,
    }


def euclidean(a: list[float], b: list[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def score_heuristic(manifest: dict[str, Any]) -> dict[str, Any]:
    image_records = manifest["images"]
    image_paths = [Path(item["path"]) for item in image_records]
    features = [image_features(path) for path in image_paths]
    valid = [item for item in features if item.get("ok")]

    count = len(image_records)
    coverage = min(20, count / 8 * 20)

    aspect_scores = []
    resolution_scores = []
    for record in image_records:
        width = record.get("width") or 0
        height = record.get("height") or 0
        if width and height:
            ratio = width / height
            aspect_scores.append(max(0, 1 - min(abs(ratio - 16 / 9), 0.4) / 0.4))
            resolution_scores.append(min(1, width / 1120))
    resolution_aspect = 20 * ((statistics.mean(aspect_scores) if aspect_scores else 0.5) * 0.55 + (statistics.mean(resolution_scores) if resolution_scores else 0.5) * 0.45)

    if len(valid) > 1:
        distances = [euclidean(valid[i]["mean"], valid[i - 1]["mean"]) for i in range(1, len(valid))]
        layout_diversity = min(20, statistics.mean(distances) / 55 * 20)
    else:
        layout_diversity = 4

    palettes = [tuple(item.get("palette", [])[:4]) for item in valid]
    repeated = len(set(color for palette in palettes for color in palette))
    palette_coherence = 15 * (1 - min(max(repeated - 8, 0), 16) / 32) if valid else 4

    richness_values = []
    for item in valid:
        contrast = min(1, item["luma_std"] / 68)
        empty_penalty = max(item["light_ratio"] - 0.82, 0) * 1.4
        too_dark_penalty = max(item["dark_ratio"] - 0.82, 0) * 1.4
        richness_values.append(max(0, contrast - empty_penalty - too_dark_penalty))
    visual_richness = 15 * (statistics.mean(richness_values) if richness_values else 0.3)

    source_text = json.dumps(manifest, ensure_ascii=False).lower()
    penalty_terms = ["logo", "watermark", "slidesgo", "freepik", "brand", "copyright"]
    safety = 10 - min(6, sum(1.2 for term in penalty_terms if term in source_text))
    if count < 3:
        safety -= 2
    reuse_safety = max(0, safety)

    component_scores = {
        "preview_coverage": round(coverage, 1),
        "resolution_and_aspect": round(resolution_aspect, 1),
        "layout_diversity": round(layout_diversity, 1),
        "palette_coherence": round(palette_coherence, 1),
        "visual_richness": round(visual_richness, 1),
        "reuse_safety": round(reuse_safety, 1),
    }
    total = round(sum(component_scores.values()), 1)
    reasons = []
    if count < 5:
        reasons.append(f"Only {count} preview images selected; page-type coverage may be thin.")
    if component_scores["layout_diversity"] < 8:
        reasons.append("Preview thumbnails are visually similar, limiting layout extraction.")
    if component_scores["reuse_safety"] < 6:
        reasons.append("Source appears to contain brand/watermark terms; distillation must stay abstract.")
    if not reasons:
        reasons.append("Heuristic metrics indicate a reusable presentation style system.")
    return {
        "mode": "heuristic",
        "component_scores": component_scores,
        "score": total,
        "reasons": reasons,
    }


def image_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def endpoint_from_base(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    if base_url.endswith("/v1"):
        return f"{base_url}/chat/completions"
    return f"{base_url}/v1/chat/completions"


def parse_json_loose(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("expected JSON object")
    return data


def vision_chat_json(system: str, user_text: str, image_paths: list[Path]) -> dict[str, Any]:
    base_url = os.environ["VISION_BASE_URL"]
    api_key = os.environ["VISION_API_KEY"]
    model = os.getenv("VISION_MODEL_NAME", "gpt-4o")
    last_error: Exception | None = None
    for attempt in range(2):
        text = user_text
        if attempt:
            text += "\n\nPrevious response was invalid. Return a single valid JSON object only, with no markdown or commentary."
        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        for path in image_paths:
            content.append({"type": "image_url", "image_url": {"url": image_data_url(path)}})
        payload = {
            "model": model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
        }
        request = urllib.request.Request(
            endpoint_from_base(base_url),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": USER_AGENT},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                data = json.loads(response.read().decode("utf-8"))
            return parse_json_loose(data["choices"][0]["message"]["content"])
        except urllib.error.HTTPError as exc:
            last_error = RuntimeError(exc.read().decode("utf-8", errors="replace")[:800])
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"vision JSON request failed: {last_error}") from last_error


def score_with_vision(manifest: dict[str, Any], image_paths: list[Path]) -> dict[str, Any] | None:
    if not (os.getenv("VISION_BASE_URL") and os.getenv("VISION_API_KEY")):
        return None
    system = "You are a strict presentation design director. Score template previews for distillation quality. Return JSON only."
    user = """
Score these web PPT template previews for whether they deserve style distillation.
Reject generic, low-resolution, inconsistent, watermark-heavy, or copyright-dependent templates.
Return JSON:
{
  "score": 0-100,
  "decision": "accept|review|reject",
  "component_scores": {
    "aesthetic_quality": 0-20,
    "professional_polish": 0-20,
    "layout_system": 0-20,
    "slide_type_coverage": 0-15,
    "originality_without_copying": 0-15,
    "abstraction_safety": 0-10
  },
  "reasons": ["..."],
  "distillation_notes": ["abstract visual rules worth keeping"]
}
""".strip()
    result = vision_chat_json(system, user, image_paths[:8])
    result["mode"] = "vision"
    return result


def make_quality_report(manifest: dict[str, Any], min_score: float) -> dict[str, Any]:
    image_paths = [Path(item["path"]) for item in manifest["images"]]
    heuristic = score_heuristic(manifest)
    vision_error = ""
    try:
        vision = score_with_vision(manifest, image_paths)
    except Exception as exc:
        vision = None
        vision_error = str(exc)
    if vision:
        score = round(heuristic["score"] * 0.35 + float(vision.get("score", 0)) * 0.65, 1)
        reasons = heuristic["reasons"] + list(vision.get("reasons", []))
    else:
        score = heuristic["score"]
        reasons = heuristic["reasons"]
        if vision_error:
            reasons.append(f"Vision scoring failed and heuristic score was used: {vision_error[:240]}")
    decision = "accept" if score >= min_score else ("review" if score >= min_score - 8 else "reject")
    if vision and vision.get("decision") == "reject":
        decision = "reject"
    return {
        "total_score": score,
        "min_score": min_score,
        "decision": decision,
        "heuristic": heuristic,
        "vision": vision,
        "vision_error": vision_error,
        "reasons": reasons,
        "image_count": len(image_paths),
    }


def ensure_profile_contract(
    manifest: dict[str, Any],
    profile: dict[str, Any],
    max_profile_repairs: int = 2,
) -> dict[str, Any]:
    """Repair and recheck the complete reusable profile after any model revision."""
    image_paths = [Path(item["path"]) for item in manifest.get("images", [])[:10]]
    expected_page_ids = [f"page-{index:02d}" for index in range(len(image_paths))]
    system = (
        "You repair a reusable presentation design-system profile. Return one complete JSON object, "
        "preserve valid visual observations, and never copy source assets or source text."
    )
    current = upgrade_legacy_profile(profile, expected_page_ids)
    for repair_number in range(1, max(0, max_profile_repairs) + 1):
        issues = profile_contract_issues(current, expected_page_ids)
        if not issues:
            return current
        repair_user = f"""
The profile below failed the reusable-profile contract. Return one complete corrected profile JSON,
not a patch. Preserve valid visual observations, source safety rules, style identity, and any visual
repair instructions already applied while fixing every structural issue. Use only these evidence page
ids: {json.dumps(expected_page_ids)}. This is structural repair {repair_number} of
{max_profile_repairs}; do not drop fields that already pass.

Contract issues:
{json.dumps(issues, ensure_ascii=False, indent=2)}

Current profile:
{json.dumps(current, ensure_ascii=False)[:18000]}

Required canonical layout_bank keys: cover, section, content, data. content and data must each have at
least two genuinely different routed archetypes. Data routing must cover a metrics-series shape and a
table or timeline shape. Every archetype needs non-empty routing, content_capacity, evidence_pages,
and a unique id. source_evidence must contain one complete record per supplied preview.
Any `_needs_visual_review` marker must be resolved from the supplied preview and removed.
""".strip()
        required_legacy_roles = _string_list(current.get("legacy_required_roles"))
        current = vision_chat_json(system, repair_user, image_paths)
        if required_legacy_roles:
            current["legacy_required_roles"] = required_legacy_roles
    remaining = profile_contract_issues(current, expected_page_ids)
    if remaining:
        raise RuntimeError(
            f"profile failed the reusable-profile contract after {max_profile_repairs} repairs: "
            + "; ".join(remaining)
        )
    return current


def _legacy_layout_observations(profile: dict[str, Any]) -> list[tuple[str, str]]:
    raw = profile.get("layout_system")
    observations: list[tuple[str, str]] = []
    if isinstance(raw, dict):
        candidates = list(raw.items())
    elif isinstance(raw, list):
        candidates = []
        for item in raw:
            text = clean_text(str(item))
            label, separator, description = text.partition(":")
            candidates.append((label if separator else "content", description if separator else text))
    else:
        candidates = []
    for label, description in candidates:
        normalized = re.sub(r"[^a-z]+", "-", str(label).lower()).strip("-")
        if normalized.startswith("cover"):
            role = "cover"
        elif normalized.startswith("agenda"):
            role = "agenda"
        elif normalized.startswith("section"):
            role = "section"
        elif normalized.startswith("comparison"):
            role = "comparison"
        elif normalized.startswith("data"):
            role = "data"
        elif normalized.startswith("quote"):
            role = "quote"
        elif normalized.startswith("closing"):
            role = "closing"
        else:
            role = "content"
        observations.append((role, clean_text(str(description))))
    return observations


def _legacy_routing(role: str, variant: str = "") -> dict[str, Any]:
    if role == "cover":
        return {"content_shapes": ["hero", "title-subtitle"], "max_items": 2}
    if role == "section":
        return {"content_shapes": ["section-divider"], "max_items": 2}
    if role == "agenda":
        return {"content_shapes": ["agenda", "numbered-list"], "min_items": 3, "max_items": 8}
    if role == "quote":
        return {"content_shapes": ["quote", "testimonial"], "max_items": 2}
    if role == "closing":
        return {"content_shapes": ["closing", "call-to-action", "contact"], "max_items": 3}
    if role == "comparison" or variant == "comparison":
        return {"content_shapes": ["comparison", "before-after"], "requires": ["paired groups"]}
    if role == "data" and variant == "table-timeline":
        return {"content_shapes": ["table", "timeline", "milestone"], "requires": ["table or timeline"]}
    if role == "data":
        return {"content_shapes": ["metrics-series", "chart", "trend"], "requires": ["metrics or series"]}
    return {"content_shapes": ["bullets", "cards", "grid"], "min_items": 2, "max_items": 6}


def _legacy_capacity(role: str, variant: str = "") -> dict[str, Any]:
    if role in {"cover", "section", "quote", "closing"}:
        return {"density": "low", "max_text_blocks": 3}
    if role == "data" and variant == "table-timeline":
        return {"density": "high", "max_rows": 6, "max_milestones": 6}
    if role == "data":
        return {"density": "high", "max_metrics": 5, "max_series_points": 8}
    if role == "comparison" or variant == "comparison":
        return {"density": "medium", "columns": 2, "max_items_per_group": 5}
    return {"density": "medium", "min_items": 2, "max_items": 6}


def upgrade_legacy_profile(
    profile: dict[str, Any], expected_page_ids: list[str]
) -> dict[str, Any]:
    """Compile complete legacy observations into the new contract before asking Vision."""
    upgraded = json.loads(json.dumps(profile))
    observations = _legacy_layout_observations(upgraded)
    exact_page_mapping = bool(observations) and len(observations) == len(expected_page_ids)

    anchors = _string_list(upgraded.get("identity_anchors"))
    if len(anchors) < 3:
        anchors.extend(_string_list(upgraded.get("core_visual")))
        anchors.extend(_string_list(upgraded.get("typography")))
        design_tokens = upgraded.get("design_tokens")
        if isinstance(design_tokens, dict):
            for key in ("shape_language", "grid", "texture", "colors"):
                anchors.extend(_string_list(design_tokens.get(key)))
        upgraded["identity_anchors"] = list(dict.fromkeys(anchors))[:5]

    evidence = upgraded.get("source_evidence")
    if not isinstance(evidence, list) or not evidence:
        evidence = []
        fallback_signature = "; ".join(_string_list(upgraded.get("core_visual")))
        for index, page_id in enumerate(expected_page_ids):
            if index < len(observations):
                role, signature = observations[index]
            else:
                role, signature = "content", fallback_signature
            record: dict[str, Any] = {
                "page_id": page_id,
                "observed_roles": [role],
                "structural_signature": signature or fallback_signature or "legacy visual system",
                "transferable_rules": [signature or fallback_signature or "preserve the legacy visual system"],
                "source_specific_risks": [
                    "Transfer abstract geometry and hierarchy only; never copy source assets or text."
                ],
            }
            if not exact_page_mapping:
                record["_needs_visual_review"] = True
            evidence.append(record)
        upgraded["source_evidence"] = evidence

    by_role: dict[str, list[tuple[str, str]]] = {}
    for index, (role, signature) in enumerate(observations):
        page_id = expected_page_ids[index] if index < len(expected_page_ids) else expected_page_ids[-1]
        by_role.setdefault(role, []).append((signature, page_id))
    required_legacy_roles = [
        role for role in ("agenda", "quote", "closing") if role in by_role
    ]
    if upgraded.get("closing_layout") and "closing" not in required_legacy_roles:
        required_legacy_roles.append("closing")
    if required_legacy_roles:
        upgraded["legacy_required_roles"] = required_legacy_roles

    def observation_for(role: str, fallback_role: str = "content") -> tuple[str, str]:
        values = by_role.get(role) or by_role.get(fallback_role) or []
        if values:
            return values[0]
        fallback_page = expected_page_ids[0] if expected_page_ids else "page-00"
        return (f"{role} composition derived from the legacy visual system", fallback_page)

    def layout(role: str, variant: str = "") -> dict[str, Any]:
        source_role = "comparison" if variant == "comparison" else role
        signature, page_id = observation_for(source_role)
        identifier = slugify(f"{role}-{variant or 'primary'}")
        item: dict[str, Any] = {
            "id": identifier,
            "composition": signature,
            "zones": [signature],
            "content_capacity": _legacy_capacity(role, variant),
            "routing": _legacy_routing(role, variant),
            "required_identity_anchors": upgraded.get("identity_anchors", [])[:3],
            "optional_variants": [],
            "avoid": ["copying source assets, source text, or an exact source arrangement"],
            "evidence_pages": [page_id],
        }
        if not exact_page_mapping:
            item["_needs_visual_review"] = True
        return item

    bank = upgraded.get("layout_bank")
    if not isinstance(bank, dict) or not bank:

        content_primary = layout("content")
        content_comparison = layout("content", "comparison")
        metrics = layout("data", "metrics-series")
        table_timeline = layout("data", "table-timeline")
        # The table/timeline archetype adapts a source-supported agenda/content grid rather than
        # claiming that the source contained the held-out validation sample.
        grid_signature, grid_page = observation_for("agenda", "content")
        table_timeline["composition"] = f"Adapt the source-supported grid into a table/timeline: {grid_signature}"
        table_timeline["zones"] = [grid_signature]
        table_timeline["evidence_pages"] = [grid_page]
        upgraded["layout_bank"] = {
            "cover": layout("cover"),
            "section": layout("section"),
            "content": [content_primary, content_comparison],
            "data": [metrics, table_timeline],
        }

    bank = upgraded.get("layout_bank")
    if isinstance(bank, dict):
        for optional_role in ("agenda", "quote", "closing"):
            if optional_role in by_role and optional_role not in bank:
                bank[optional_role] = layout(optional_role)

    upgraded.setdefault(
        "density_rules",
        {
            "low": "preserve a single focal composition and generous whitespace",
            "medium": "use the legacy grid with two to six concise content groups",
            "high": "reduce decoration before reducing label size or hierarchy",
        },
    )
    upgraded.setdefault(
        "variation_rules",
        ["Vary image/text balance and grid emphasis while preserving the legacy identity anchors."],
    )
    upgraded.setdefault(
        "anti_repetition_rules",
        ["Do not repeat the same primary composition on adjacent slides."],
    )
    return upgraded


def preserve_legacy_sidecar_roles(
    profile: dict[str, Any],
    legacy_sidecar: dict[str, Any],
    expected_page_ids: list[str],
) -> dict[str, Any]:
    """Restore missing optional roles from the installed abstract runtime sidecar."""
    upgraded = json.loads(json.dumps(profile))
    bank = upgraded.get("layout_bank")
    if not isinstance(bank, dict):
        return upgraded
    required = _string_list(upgraded.get("legacy_required_roles"))
    layouts = legacy_sidecar.get("layouts")
    if not isinstance(layouts, list):
        return upgraded
    for index, legacy in enumerate(layouts):
        if not isinstance(legacy, dict):
            continue
        role = clean_text(str(legacy.get("semantic_role") or legacy.get("page_type") or "")).lower()
        if role not in {"agenda", "quote", "closing"}:
            continue
        if role not in required:
            required.append(role)
        if role in bank:
            continue
        page_id = (
            expected_page_ids[index]
            if index < len(expected_page_ids)
            else (expected_page_ids[-1] if expected_page_ids else "page-00")
        )
        summary = clean_text(
            str(
                legacy.get("summary")
                or legacy.get("visual_signature")
                or f"preserved legacy {role} composition"
            )
        )
        bank[role] = {
            "id": slugify(str(legacy.get("id") or f"{role}-legacy")),
            "composition": summary,
            "zones": _string_list(legacy.get("zones"))
            or _string_list(legacy.get("visual_signature"))
            or [summary],
            "content_capacity": legacy.get("content_capacity") or _legacy_capacity(role),
            "routing": legacy.get("routing") or _legacy_routing(role),
            "required_identity_anchors": upgraded.get("identity_anchors", [])[:3],
            "optional_variants": _string_list(legacy.get("variation_tags")),
            "avoid": _string_list(legacy.get("avoid_for"))
            or ["copying source assets, source text, or an exact source arrangement"],
            "evidence_pages": [page_id],
        }
    if required:
        upgraded["legacy_required_roles"] = required
    return upgraded


def distill_profile(
    manifest: dict[str, Any],
    quality: dict[str, Any],
    style_id: str,
    style_name: str,
    max_profile_repairs: int = 2,
) -> dict[str, Any]:
    image_paths = [Path(item["path"]) for item in manifest["images"]]
    if not (os.getenv("VISION_BASE_URL") and os.getenv("VISION_API_KEY")):
        raise RuntimeError("VISION_BASE_URL/VISION_API_KEY not configured")
    system = (
        "You are a senior presentation designer. Distill reusable style rules from references. "
        "Never copy source images, icons, logos, characters, watermarks, or text. Return JSON only."
    )
    grammar_fields = """
identity_anchors, source_evidence, layout_bank, density_rules, variation_rules, anti_repetition_rules.
identity_anchors should name 3-5 abstract traits that must survive every page role.
source_evidence should contain one record per input preview using page ids page-00, page-01, etc.;
each record should include observed_roles, structural_signature, transferable_rules, and
source_specific_risks. Describe abstract evidence only, never source text or assets.
layout_bank should be an object keyed by page role. A role may contain one layout object or a list of
2-4 genuinely different layout archetypes. Each archetype should contain id, composition, zones,
content_capacity, routing, required_identity_anchors, optional_variants, avoid, and evidence_pages.
routing should use machine-readable hints such as content_shapes, min_items, max_items, requires,
and excludes. Do not encode one validation sample's exact item count as a universal role rule.
The canonical cover, section, content, and data keys are required. content and data must each contain
at least two archetypes. The data archetypes must cover both metrics-series and table/timeline shapes.
Every archetype must have non-empty routing, content_capacity, and evidence_pages containing only the
page ids declared in source_evidence. Do not invent alternate role names such as content_list or grid
instead of the canonical keys; express those distinctions as archetypes inside content or data.
density_rules should define low, medium, and high-density adaptations.
variation_rules should explain how layouts vary while preserving identity.
anti_repetition_rules should prevent the same composition from being reused across the deck.
""".strip()
    user = f"""
Distill these accepted template previews into a reusable gpt-image2-ppt style profile.
Style id: {style_id}
Style name: {style_name}
Quality report: {json.dumps(quality, ensure_ascii=False)[:3500]}

The input previews are ordered page-00, page-01, page-02, and so on.

Return JSON with:
style_id, style_name_zh, style_name_en, description, palette,
core_visual, typography, cover_layout, content_layout, data_layout,
section_layout, closing_layout, forbidden, scenarios,
design_tokens, layout_system, image_treatment, iconography, chart_style,
do_not_copy, provenance_summary.
All list fields should be concise bullet strings.
design_tokens should include colors, fonts, spacing, shape_language, texture, grid, motion_or_depth.
layout_system should describe reusable patterns for cover, agenda, section, content, comparison, data, quote, closing.
{grammar_fields}
provenance_summary must mention only source URL and abstract observations, not original copy.
""".strip()
    profile = vision_chat_json(system, user, image_paths[:10])
    return ensure_profile_contract(manifest, profile, max_profile_repairs)


def bullets(items: Any, fallback: str) -> str:
    if isinstance(items, dict):
        rendered: list[str] = []
        for key, value in items.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            rendered.append(f"- {clean_text(str(key))}: {clean_text(str(value))}")
        return "\n".join(rendered) if rendered else f"- {fallback}"
    if isinstance(items, str):
        items = [items]
    if not isinstance(items, list) or not items:
        items = [fallback]
    return "\n".join(f"- {clean_text(str(item))}" for item in items if clean_text(str(item)))


def render_style_markdown(
    profile: dict[str, Any],
    style_id: str,
    style_name: str,
) -> str:
    zh = clean_text(str(profile.get("style_name_zh") or style_name))
    en = clean_text(str(profile.get("style_name_en") or style_name))
    palette = profile.get("palette") or []
    palette_text = "、".join(str(item) for item in palette) if palette else "主色、辅助色、中性色按参考风格抽象使用"
    scenarios = profile.get("scenarios") or ["商业汇报", "产品介绍", "课程培训", "项目提案"]
    design_tokens = profile.get("design_tokens") or {}
    if isinstance(design_tokens, dict):
        token_lines = []
        for key in ["colors", "fonts", "spacing", "shape_language", "texture", "grid", "motion_or_depth"]:
            value = design_tokens.get(key)
            if isinstance(value, list):
                value = "；".join(clean_text(str(item)) for item in value)
            if value:
                token_lines.append(f"- {key}: {clean_text(str(value))}")
        tokens_text = "\n".join(token_lines) if token_lines else "- 使用 profile 中的配色、字体、间距、形状、纹理和网格规则。"
    else:
        tokens_text = bullets(design_tokens, "使用 profile 中的配色、字体、间距、形状、纹理和网格规则。")
    identity_section = f"""
【不可丢失的风格锚点】
{bullets(profile.get("identity_anchors"), "每一页都必须保留 3-5 个稳定、抽象且不可替代的风格身份特征。")}

"""
    grammar_sections = f"""
【页面类型布局库】
{bullets(profile.get("layout_bank"), "为封面、章节、内容、对比、数据和收尾定义各自的构图、内容区域、容量、身份锚点和可选变体。")}

【内容密度适配】
{bullets(profile.get("density_rules"), "低密度强调单一焦点，中密度使用稳定网格，高密度优先压缩装饰而不是压缩字号。")}

【变化与防重复】
{bullets(profile.get("variation_rules"), "在保持网格、色彩比例和形状语言的前提下改变视觉重心。")}
{bullets(profile.get("anti_repetition_rules"), "连续页面不得复用完全相同的主构图和装饰位置。")}

"""
    return f"""# {zh} / {en}

## 风格ID
{style_id}

## 风格名称
{zh} / {en}

## 风格描述
{clean_text(str(profile.get("description") or "从高质量在线 PPT 模板预览中抽象出的可复用视觉风格。"))}

来源说明：本文件只记录抽象视觉规律，不包含原模板图片、插画、图标、照片、logo、水印或原始文案。

## 设计令牌
{tokens_text}

## 基础提示词模板

你是一位资深演示文稿视觉设计师。请生成 16:9 横版幻灯片，并使用「{zh} / {en}」风格。只能迁移抽象设计规律，不得复刻任何来源模板页面或素材。

【核心视觉】
{bullets(profile.get("core_visual"), "建立清晰的视觉系统：稳定网格、统一色彩、明确层级和一致的装饰语汇。")}
- 推荐配色：{palette_text}
{identity_section}【字体】
{bullets(profile.get("typography"), "中文使用思源黑体 / 苹方，英文使用 Inter / Helvetica Neue，标题、正文和注释形成明确层级。")}

【封面页构图】
{bullets(profile.get("cover_layout"), "使用强标题、弱副标题和少量图形/图片区域建立第一眼识别度。")}

【内容页构图】
{bullets(profile.get("content_layout"), "标题区稳定，主体采用 2-3 个信息块、图文并置、步骤或卡片结构。")}

【布局系统】
{bullets(profile.get("layout_system"), "复用稳定页面骨架：封面、目录、章节、内容、对比、数据、引用、收尾都应共享相同网格和视觉节奏。")}
{grammar_sections}【图片处理】
{bullets(profile.get("image_treatment"), "图片只使用新生成或用户提供素材，处理方式应遵循统一裁切、遮罩、色调和叠加规则。")}

【图标与装饰】
{bullets(profile.get("iconography"), "图标、线条和装饰形状应统一笔触、圆角、粗细和复杂度。")}

【数据页构图】
{bullets(profile.get("data_layout"), "用大数字、简洁图表、对比卡片或指标组表达数据，避免复杂小字。")}

【图表风格】
{bullets(profile.get("chart_style"), "图表保持简洁高对比，颜色、线宽、标签样式与整体视觉一致。")}

【章节页构图】
{bullets(profile.get("section_layout"), "章节页使用更强留白、页码或短标题形成节奏停顿。")}

【收尾页构图】
{bullets(profile.get("closing_layout"), "保留核心色彩和图形语言，用简洁感谢语、行动号召或联系信息收束。")}

【禁止】
{bullets(profile.get("forbidden"), "禁止复制参考图中的原始图片、插画、图标、logo、角色、独特版式组合和原文案。")}
{bullets(profile.get("do_not_copy"), "不要复制任何来源页独有构图、素材、人物、品牌、模板署名或可识别元素。")}
- 禁止出现来源网站 UI、水印、下载提示或模板署名。

## 适用场景
{"、".join(clean_text(str(item)) for item in scenarios)}。
"""


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [clean_text(str(item)) for item in value if clean_text(str(item))]
    if value is None:
        return []
    text = clean_text(str(value))
    return [text] if text else []


def _layout_entries_for_role(role: str, raw_entry: Any) -> list[dict[str, Any]]:
    """Normalize compact single-archetype and multi-archetype role layouts."""
    if isinstance(raw_entry, list):
        entries = raw_entry
    elif isinstance(raw_entry, dict) and isinstance(raw_entry.get("variants"), list):
        defaults = {key: value for key, value in raw_entry.items() if key != "variants"}
        entries = []
        for variant in raw_entry["variants"]:
            if isinstance(variant, dict):
                entries.append({**defaults, **variant})
            else:
                entries.append({**defaults, "composition": variant})
    else:
        entries = [raw_entry]
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        if isinstance(entry, dict):
            normalized.append(dict(entry))
        elif entry is not None:
            normalized.append({"composition": entry})
    return normalized or [{"composition": f"{role} layout"}]


def profile_contract_issues(
    profile: dict[str, Any],
    expected_page_ids: list[str],
) -> list[str]:
    """Return structural blockers before any paid validation image is generated."""
    issues: list[str] = []
    anchors = _string_list(profile.get("identity_anchors"))
    if len(anchors) < 3:
        issues.append("identity_anchors must contain at least three abstract anchors")

    expected = set(expected_page_ids)
    evidence = profile.get("source_evidence")
    if not isinstance(evidence, list):
        evidence = []
    evidence_ids: list[str] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        page_id = clean_text(str(item.get("page_id") or ""))
        if item.get("_needs_visual_review"):
            issues.append(f"source_evidence {page_id or '<unknown>'} needs visual review")
        if page_id:
            evidence_ids.append(page_id)
        for field in (
            "observed_roles",
            "structural_signature",
            "transferable_rules",
            "source_specific_risks",
        ):
            if not item.get(field):
                issues.append(f"source_evidence {page_id or '<unknown>'} missing {field}")
    found = set(evidence_ids)
    if found != expected or len(evidence_ids) != len(expected_page_ids):
        missing = sorted(expected - found)
        extra = sorted(found - expected)
        issues.append(
            f"source_evidence must map every preview exactly once; missing={missing}, extra={extra}"
        )

    bank = profile.get("layout_bank")
    if not isinstance(bank, dict):
        bank = {}
    required_roles = ("cover", "section", "content", "data")
    for role in required_roles:
        if role not in bank:
            issues.append(f"layout_bank missing canonical role {role}")
    for role in _string_list(profile.get("legacy_required_roles")):
        if role not in bank:
            issues.append(f"layout_bank missing preserved legacy role {role}")
    for role in ("content", "data"):
        if role in bank and len(_layout_entries_for_role(role, bank[role])) < 2:
            issues.append(f"layout_bank.{role} must contain at least two archetypes")

    layout_ids: list[str] = []
    data_shapes: set[str] = set()
    for role, raw_entry in bank.items():
        for index, entry in enumerate(_layout_entries_for_role(role, raw_entry), start=1):
            label = clean_text(str(entry.get("id") or f"{role}[{index}]"))
            layout_ids.append(label)
            if entry.get("_needs_visual_review"):
                issues.append(f"layout {label} needs visual review")
            routing = entry.get("routing")
            if not isinstance(routing, dict) or not routing:
                issues.append(f"layout {label} missing non-empty routing")
                routing = {}
            shapes = routing.get("content_shapes")
            if isinstance(shapes, str):
                shapes = [shapes]
            if role == "data" and isinstance(shapes, list):
                data_shapes.update(clean_text(str(value)).lower() for value in shapes)
            capacity = entry.get("content_capacity")
            if capacity is None or capacity == "" or capacity == [] or capacity == {}:
                issues.append(f"layout {label} missing non-empty content_capacity")
            pages = _string_list(entry.get("evidence_pages"))
            if not pages:
                issues.append(f"layout {label} missing evidence_pages")
            invalid_pages = sorted(set(pages) - expected)
            if invalid_pages:
                issues.append(f"layout {label} references unknown evidence pages {invalid_pages}")
    if len(layout_ids) != len(set(layout_ids)):
        issues.append("layout ids must be unique")
    normalized_shapes = {
        re.sub(r"[^a-z0-9]+", "-", value).strip("-") for value in data_shapes
    }
    has_metrics = any(
        any(part in shape for part in ("metric", "kpi", "chart", "series", "trend"))
        for shape in normalized_shapes
    )
    has_table_or_timeline = any(
        any(part in shape for part in ("table", "tabular", "matrix", "timeline", "milestone", "roadmap"))
        for shape in normalized_shapes
    )
    if bank and not has_metrics:
        issues.append("layout_bank.data routing must cover metrics-series content")
    if bank and not has_table_or_timeline:
        issues.append("layout_bank.data routing must cover table or timeline content")
    return list(dict.fromkeys(issues))


def build_layout_sidecar(
    profile: dict[str, Any],
    style_id: str,
    source_hash: str = "",
) -> dict[str, Any]:
    """Compile distilled layout grammar into generate_ppt's sidecar contract."""
    raw_bank = profile.get("layout_bank")
    bank: dict[str, Any] = raw_bank if isinstance(raw_bank, dict) else {}
    if not bank:
        for role, field in [
            ("cover", "cover_layout"),
            ("section", "section_layout"),
            ("content", "content_layout"),
            ("data", "data_layout"),
            ("closing", "closing_layout"),
        ]:
            if profile.get(field):
                bank[role] = {"composition": profile[field]}
    if not bank:
        bank["content"] = {
            "composition": "Use the distilled grid, identity anchors, and typography hierarchy for a general content page.",
            "content_capacity": {"density": "medium"},
        }

    page_type_map = {
        "cover": "cover",
        "agenda": "agenda",
        "section": "section",
        "data": "data",
        "table": "data",
        "metrics": "data",
        "quote": "quote",
        "closing": "closing",
    }
    layouts: list[dict[str, Any]] = []
    identity = _string_list(profile.get("identity_anchors"))
    flattened: list[tuple[str, dict[str, Any]]] = []
    for role, raw_entry in bank.items():
        flattened.extend((role, entry) for entry in _layout_entries_for_role(role, raw_entry))

    for index, (role, entry) in enumerate(flattened, start=1):
        composition = entry.get("composition") or entry.get("summary") or f"{role} layout"
        if isinstance(composition, (dict, list)):
            composition = json.dumps(composition, ensure_ascii=False, separators=(",", ":"))
        zones = entry.get("zones")
        anchors = _string_list(entry.get("required_identity_anchors")) or identity
        signature_parts = [clean_text(str(composition))]
        if zones:
            signature_parts.append(
                "zones=" + json.dumps(zones, ensure_ascii=False, separators=(",", ":"))
            )
        if anchors:
            signature_parts.append("anchors=" + "; ".join(anchors))
        avoid = entry.get("avoid")
        variants = entry.get("optional_variants")
        layout_id = clean_text(str(entry.get("id") or "")) or f"{slugify(role, 'layout')}-{index:02d}"
        routing = entry.get("routing") if isinstance(entry.get("routing"), dict) else {}
        layouts.append(
            {
                "id": layout_id,
                "page_index": index - 1,
                "page_type": clean_text(str(entry.get("page_type") or "")) or page_type_map.get(role, "content"),
                "semantic_role": clean_text(str(entry.get("semantic_role") or "")) or role,
                "summary": clean_text(str(composition)),
                "visual_signature": " | ".join(signature_parts),
                "content_capacity": entry.get("content_capacity") or {},
                "best_for": _string_list(entry.get("best_for")) or [role],
                "avoid_for": _string_list(avoid),
                "variation_tags": _string_list(variants),
                "routing": routing,
                "evidence_pages": _string_list(entry.get("evidence_pages")),
                "validation_default": bool(entry.get("validation_default", False)),
                "reuse_friendly": bool(entry.get("reuse_friendly", role not in {"cover", "section", "closing"})),
                "reuse_reason": clean_text(str(entry.get("reuse_reason") or "")) or ("Distinctive rhythm page" if role in {"cover", "section", "closing"} else "Reusable with variation rules"),
                "external_image_slots": entry.get("external_image_slots") if isinstance(entry.get("external_image_slots"), list) else [],
                "reference_image": None,
            }
        )

    return {
        "version": "2",
        "style_id": style_id,
        "source": "web-template-distillation",
        "source_hash": source_hash,
        "global_style": clean_text(str(profile.get("description") or "")),
        "theme": {
            "palette": profile.get("palette") or [],
            "identity_anchors": identity,
            "density_rules": profile.get("density_rules") or {},
            "variation_rules": profile.get("variation_rules") or [],
            "anti_repetition_rules": profile.get("anti_repetition_rules") or [],
        },
        "layouts": layouts,
    }


def write_style_pair(
    output_path: Path,
    style_markdown: str,
    profile: dict[str, Any],
    style_id: str,
    source_hash: str = "",
) -> Path:
    """Write the only executable distilled-style contract: Markdown plus sidecar."""
    sidecar_path = output_path.with_suffix(".layouts.json")
    sidecar = build_layout_sidecar(profile, style_id, source_hash)
    if not sidecar.get("layouts"):
        raise RuntimeError("distilled style produced an empty layout sidecar")
    sidecar_text = json.dumps(sidecar, ensure_ascii=False, indent=2)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_suffix = f".tmp-{os.getpid()}"
    style_temp = output_path.with_name(output_path.name + temp_suffix)
    sidecar_temp = sidecar_path.with_name(sidecar_path.name + temp_suffix)
    try:
        style_temp.write_text(style_markdown, encoding="utf-8")
        sidecar_temp.write_text(sidecar_text, encoding="utf-8")
        # Publish the machine contract first. If the second replace is interrupted,
        # callers still cannot discover a new Markdown-only style.
        sidecar_temp.replace(sidecar_path)
        style_temp.replace(output_path)
    finally:
        style_temp.unlink(missing_ok=True)
        sidecar_temp.unlink(missing_ok=True)
    return sidecar_path


def write_manual_prompt(
    path: Path,
    manifest: dict[str, Any],
    quality: dict[str, Any],
    style_id: str,
    style_name: str,
    styles_dir: Path = DEFAULT_STYLES_DIR,
) -> None:
    lines = "\n".join(f"- {item['path']}" for item in manifest["images"])
    path.write_text(
        f"""# Manual Distillation Prompt

这些模板预览已通过质量筛选，请从中蒸馏可直接运行的 gpt-image2-ppt 结构化风格包。

风格 ID：`{style_id}`
风格名称：`{style_name}`
质量报告：`quality_report.json`，总分 {quality["total_score"]}，决策 {quality["decision"]}

要求：
- 只抽象配色、网格、字体气质、版式、装饰语汇、页面类型规则。
- 不要复制来源图片、插画、图标、照片、logo、水印、原文案或可识别素材。
- 先写 `style_profile.json` 作为权威源，再由它派生以下配对文件；不得只生成 Markdown：
  - `{styles_dir / (style_id + ".md")}`
  - `{styles_dir / (style_id + ".layouts.json")}`
- 必须包含 `## 基础提示词模板`，以便 gpt-image2-ppt-skills 加载。
- `style_profile.json` 字段包含：style_id、style_name_zh/en、description、palette、design_tokens、layout_system、identity_anchors、source_evidence、layout_bank、density_rules、variation_rules、anti_repetition_rules、typography、image_treatment、iconography、chart_style、cover/content/data/section/closing layout、forbidden、do_not_copy、scenarios、provenance_summary。
- `layout_bank` 至少包含 cover、section、content、data；content 与 data 各至少两个带 routing、content_capacity、evidence_pages 的原型，data 同时覆盖 metrics-series 和 table/timeline。
- 风格文件必须足够具体：下次只读这个文件，也能基本还原该模板的抽象风格，包括颜色比例、标题层级、图形语言、图片裁切方式、常见页面骨架、图表样式和禁用项。

图片：
{lines}
""",
        encoding="utf-8",
    )


def parse_validation_roles(value: str | None) -> list[str]:
    roles = [item.strip().lower() for item in (value or "").split(",") if item.strip()]
    if not roles:
        roles = list(DEFAULT_VALIDATION_ROLES)
    unknown = [role for role in roles if role not in VALIDATION_SCENARIOS]
    if unknown:
        raise ValueError(
            f"unknown validation roles: {', '.join(unknown)}; "
            f"choose from {', '.join(VALIDATION_SCENARIOS)}"
        )
    return list(dict.fromkeys(roles))


def select_validation_roles(
    value: str | None,
    closed_loop: bool,
    suite: str = "standard",
) -> list[str]:
    if value:
        return parse_validation_roles(value)
    if closed_loop and suite == "generalization":
        return list(GENERALIZATION_VALIDATION_CASES)
    return list(DEFAULT_VALIDATION_ROLES) if closed_loop else ["cover"]


def validation_terminal_status(validation_status: str, closed_loop: bool) -> str:
    if validation_status == "reject":
        return "validation_reject"
    if not closed_loop:
        return "distilled"
    if validation_status == "accept":
        return "validated"
    return "validation_review"


def validation_prompt_from_style(
    style_md: str,
    style_name: str,
    role: str = "cover",
    layout_directive: str = "",
) -> str:
    scenario = VALIDATION_SCENARIOS[role]
    compiled_layout = (
        f"\nCompiled layout directive consumed by the production renderer:\n{layout_directive[:3500]}\n"
        if layout_directive
        else ""
    )
    return f"""
Generate one original 16:9 {role} slide for a professional presentation.
Validation purpose: {scenario['purpose']}
Use exactly this neutral test content: {scenario['content']}

Use the distilled style below as the design system. Preserve its abstract visual identity through
layout grammar, palette ratios, typography mood, spacing, image treatment, chart language, and
decorative vocabulary. Adapt the system to this page role instead of copying a source composition.
Keep every supplied text item legible. Do not add source-template text. Do not copy any source image,
icon, person, logo, watermark, website UI, or uniquely identifiable arrangement.
The compiled layout directive overrides generic role suggestions in the longer style text. Before
finalizing, verify every supplied word and number appears exactly once, with no missing, duplicated,
misspelled, merged, or garbled labels. Text accuracy is a hard validation gate; simplify decoration
and enlarge text before sacrificing spelling or readability. Treat every visible numeral, sequence
marker, date, footer, eyebrow, legend, axis label, badge, and section code as text: if it is not in the
neutral test content, do not generate it. When a layout archetype normally uses decorative numbers or
labels, replace them with non-text geometry or supplied labels instead of inventing new content.

Style name: {style_name}
{compiled_layout}
Distilled style:
{style_md[:7500]}
""".strip()


def generate_validation_image(
    style_md: str,
    style_name: str,
    output_path: Path,
    role: str = "cover",
    layout_directive: str = "",
) -> Path:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY not configured")
    candidates = [
        REPO_ROOT / "scripts",
        Path.home() / ".codex/skills/gpt-image2-ppt-skills/scripts",
        Path.home() / ".claude/skills/gpt-image2-ppt-skills/scripts",
    ]
    scripts_dir = next(
        (path for path in candidates if (path / "image_generator.py").is_file()),
        None,
    )
    if scripts_dir is None:
        raise RuntimeError(
            "gpt-image2-ppt image_generator.py was not found; run this skill inside the repository "
            "or install gpt-image2-ppt-skills for the active agent."
        )
    sys.path.insert(0, str(scripts_dir))
    try:
        from image_generator import GptImage2Generator
    finally:
        try:
            sys.path.remove(str(scripts_dir))
        except ValueError:
            pass
    generator = GptImage2Generator(aspect_ratio="16:9")
    generator.generate_scene_image(
        {
            "index": 1,
            "image_prompt": validation_prompt_from_style(
                style_md, style_name, role, layout_directive
            ),
        },
        str(output_path),
    )
    return output_path


def select_validation_layout(
    validation_case: str,
    layout_sidecar: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Select a validation layout through the production content router."""
    if not layout_sidecar:
        return None
    scenario = VALIDATION_SCENARIOS[validation_case]
    page_type = scenario.get("page_type") or (
        validation_case
        if validation_case in {"cover", "agenda", "section", "data", "quote", "closing"}
        else "content"
    )
    scripts_dir = REPO_ROOT / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        from template_analyzer import assign_layouts
    finally:
        try:
            sys.path.remove(str(scripts_dir))
        except ValueError:
            pass
    assigned = assign_layouts(
        [
            {
                "slide_number": 1,
                "page_type": page_type,
                "content": scenario["content"],
            }
        ],
        layout_sidecar,
    )
    return assigned.get(1)


def generate_validation_deck(
    style_md: str,
    style_name: str,
    output_dir: Path,
    roles: list[str],
    layout_sidecar: dict[str, Any] | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: dict[str, Path] = {}
    outer_attempts = max(1, int(os.getenv("DISTILL_IMAGE_RETRY_ROUNDS", "1")))
    outer_delay = max(0.0, float(os.getenv("DISTILL_IMAGE_RETRY_DELAY_SECS", "30")))
    for role in roles:
        path = output_dir / f"{role}.png"
        if path.is_file() and path.stat().st_size > 1024:
            print(f"[reuse] validation image: {path}")
            generated[role] = path
            continue
        directive = ""
        matched = select_validation_layout(role, layout_sidecar)
        if matched:
            directive = json.dumps(matched, ensure_ascii=False, separators=(",", ":"))
        last_error: Exception | None = None
        for attempt in range(1, outer_attempts + 1):
            try:
                generate_validation_image(style_md, style_name, path, role, directive)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if attempt >= outer_attempts:
                    break
                print(
                    f"[retry] validation role={role} outer attempt {attempt}/{outer_attempts} "
                    f"failed: {exc}; wait {outer_delay:.0f}s"
                )
                time.sleep(outer_delay)
        if last_error is not None:
            raise last_error
        generated[role] = path
    return generated


def load_style_pair(style_path: Path) -> tuple[str, dict[str, Any]]:
    """Load an executable style pair for same-prompt migration comparison."""
    sidecar_path = style_path.with_suffix(".layouts.json")
    missing = [str(path) for path in (style_path, sidecar_path) if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "baseline style must be an executable .md + .layouts.json pair; missing: "
            + ", ".join(missing)
        )
    style_md = style_path.read_text(encoding="utf-8")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    if not isinstance(sidecar, dict) or not isinstance(sidecar.get("layouts"), list):
        raise ValueError(f"invalid baseline layout sidecar: {sidecar_path}")
    return style_md, sidecar


def validate_migration_pair(
    manifest: dict[str, Any],
    baseline_images: dict[str, Path],
    candidate_images: dict[str, Path],
    roles: list[str],
) -> dict[str, Any]:
    """Ask one evaluator to compare old and new outputs generated from identical cases."""
    if not (os.getenv("VISION_BASE_URL") and os.getenv("VISION_API_KEY")):
        raise RuntimeError("VISION_BASE_URL/VISION_API_KEY not configured")
    reference_paths = [Path(item["path"]) for item in manifest.get("images", [])[:4]]
    image_paths = (
        reference_paths
        + [baseline_images[role] for role in roles]
        + [candidate_images[role] for role in roles]
    )
    system = (
        "You are a strict presentation-system migration evaluator. Compare an installed baseline "
        "style and a migrated candidate generated from identical held-out content. Return JSON only."
    )
    user = f"""
The first {len(reference_paths)} images are source-template previews. Next come BASELINE pages in this
order: {json.dumps(roles)}. Last come CANDIDATE pages in the same order: {json.dumps(roles)}.

Score both decks independently, then compare them role by role. Reward reusable style identity,
role fitness, readable and exact supplied text, coherent cross-page variation, and successful transfer
to held-out content. Penalize generic AI styling, invented text, repeated composition, identity drift,
source copying, or a candidate that is structurally richer but visually worse. Do not favor the
candidate merely because it is newer.

Return JSON:
{{
  "baseline_aggregate_score": 0-100,
  "candidate_aggregate_score": 0-100,
  "baseline_copying_risk": "low|medium|high",
  "candidate_copying_risk": "low|medium|high",
  "role_results": {{
    "<role>": {{
      "baseline_fit_score": 0-100,
      "candidate_fit_score": 0-100,
      "baseline_readability_score": 0-100,
      "candidate_readability_score": 0-100,
      "candidate_text_accuracy_score": 0-100,
      "candidate_improvements": ["specific visible gains"],
      "candidate_regressions": ["specific visible losses"]
    }}
  }},
  "system_improvements": ["cross-page gains"],
  "system_regressions": ["cross-page losses"],
  "decision": "promote|keep-baseline|review",
  "rationale": "concise evidence-based decision"
}}
""".strip()
    return vision_chat_json(system, user, image_paths)


def normalize_migration_comparison(
    report: dict[str, Any],
    roles: list[str],
    *,
    candidate_validation_passed: bool,
    min_improvement: float,
    max_regression: float,
    min_text_accuracy: float,
) -> dict[str, Any]:
    """Apply deterministic promotion gates to the pairwise visual evaluation."""
    normalized = dict(report)

    def number(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    baseline_aggregate = number(normalized.get("baseline_aggregate_score"))
    candidate_aggregate = number(normalized.get("candidate_aggregate_score"))
    aggregate_gain = candidate_aggregate - baseline_aggregate
    raw_roles = normalized.get("role_results")
    role_results = raw_roles if isinstance(raw_roles, dict) else {}
    missing_roles = [role for role in roles if not isinstance(role_results.get(role), dict)]
    fit_deltas: dict[str, float] = {}
    readability_deltas: dict[str, float] = {}
    text_scores: dict[str, float] = {}
    for role in roles:
        values = role_results.get(role) if isinstance(role_results.get(role), dict) else {}
        fit_deltas[role] = number(values.get("candidate_fit_score")) - number(
            values.get("baseline_fit_score")
        )
        readability_deltas[role] = number(
            values.get("candidate_readability_score")
        ) - number(values.get("baseline_readability_score"))
        text_scores[role] = number(values.get("candidate_text_accuracy_score"))

    copy_rank = {"low": 0, "medium": 1, "high": 2}
    baseline_copy = str(normalized.get("baseline_copying_risk", "medium")).lower()
    candidate_copy = str(normalized.get("candidate_copying_risk", "medium")).lower()
    copying_not_worse = copy_rank.get(candidate_copy, 1) <= copy_rank.get(
        baseline_copy, 1
    )
    decision = str(normalized.get("decision", "review")).lower()
    maximum_fit_regression = max(
        (max(0.0, -delta) for delta in fit_deltas.values()), default=0.0
    )
    maximum_readability_regression = max(
        (max(0.0, -delta) for delta in readability_deltas.values()), default=0.0
    )
    minimum_text_score = min(text_scores.values(), default=0.0)
    promoted = (
        candidate_validation_passed
        and decision == "promote"
        and not missing_roles
        and aggregate_gain >= min_improvement
        and maximum_fit_regression <= max_regression
        and maximum_readability_regression <= max_regression
        and minimum_text_score >= min_text_accuracy
        and candidate_copy == "low"
        and copying_not_worse
    )
    reasons: list[str] = []
    if not candidate_validation_passed:
        reasons.append("candidate did not pass its standalone closed-loop gate")
    if decision != "promote":
        reasons.append(f"pairwise evaluator decision was {decision}")
    if missing_roles:
        reasons.append(f"pairwise evaluator omitted roles: {', '.join(missing_roles)}")
    if aggregate_gain < min_improvement:
        reasons.append(
            f"aggregate gain {aggregate_gain:.1f} did not reach {min_improvement:.1f}"
        )
    if maximum_fit_regression > max_regression:
        reasons.append(
            f"role fit regression {maximum_fit_regression:.1f} exceeded {max_regression:.1f}"
        )
    if maximum_readability_regression > max_regression:
        reasons.append(
            "readability regression "
            f"{maximum_readability_regression:.1f} exceeded {max_regression:.1f}"
        )
    if minimum_text_score < min_text_accuracy:
        reasons.append(
            f"candidate text accuracy {minimum_text_score:.1f} was below {min_text_accuracy:.1f}"
        )
    if candidate_copy != "low" or not copying_not_worse:
        reasons.append(
            f"copying risk baseline={baseline_copy}, candidate={candidate_copy}"
        )
    normalized.update(
        {
            "roles": roles,
            "baseline_aggregate_score": baseline_aggregate,
            "candidate_aggregate_score": candidate_aggregate,
            "aggregate_gain": aggregate_gain,
            "fit_deltas": fit_deltas,
            "readability_deltas": readability_deltas,
            "minimum_candidate_text_accuracy": minimum_text_score,
            "maximum_fit_regression": maximum_fit_regression,
            "maximum_readability_regression": maximum_readability_regression,
            "copying_not_worse": copying_not_worse,
            "missing_roles": missing_roles,
            "promotion_thresholds": {
                "aggregate_gain": min_improvement,
                "maximum_role_regression": max_regression,
                "candidate_text_accuracy": min_text_accuracy,
                "candidate_copying_risk": "low",
            },
            "promoted": promoted,
            "reasons": reasons,
        }
    )
    return normalized


def validate_style_fit(
    manifest: dict[str, Any],
    style_md: str,
    validation_images: dict[str, Path] | Path,
    source_evidence: Any = None,
) -> dict[str, Any] | None:
    if not (os.getenv("VISION_BASE_URL") and os.getenv("VISION_API_KEY")):
        return None
    if isinstance(validation_images, Path):
        validation_images = {"cover": validation_images}
    reference_paths = [Path(item["path"]) for item in manifest.get("images", [])[:8]]
    generated_roles = list(validation_images)
    image_paths = reference_paths + [validation_images[role] for role in generated_roles]
    system = (
        "You are a strict presentation design-system evaluator. Compare a generated multi-page "
        "validation deck to source references. Judge abstract transfer, not pixel similarity. Return JSON only."
    )
    user = f"""
The first {len(reference_paths)} images are source template previews. The remaining images are newly generated
validation pages in this exact order: {json.dumps(generated_roles)}.

Judge whether the generated pages preserve one coherent abstract design system without copying source assets.
Evaluate every page role independently. Penalize illegible test content, generic AI styling, repeated composition,
identity drift between roles, and dependence on an exact source arrangement. A strong result should look like a new
deck by the same design system, not a collage or near-copy.

Return JSON:
{{
  "aggregate_score": 0-100,
  "identity_score": 0-100,
  "deck_consistency_score": 0-100,
  "layout_transfer_score": 0-100,
  "copying_risk": "low|medium|high",
  "page_results": {{
    "<role>": {{
      "fit_score": 0-100,
      "readability_score": 0-100,
      "role_fitness_score": 0-100,
      "text_accuracy_score": 0-100,
      "text_errors": ["missing, duplicated, misspelled, or garbled supplied text"],
      "matches": ["specific transferable rules that worked"],
      "mismatches": ["specific failures"]
    }}
  }},
  "system_matches": ["rules consistently preserved across pages"],
  "system_mismatches": ["systemic failures across pages"],
  "repair_actions": [
    {{"target": "profile field or page role", "problem": "diagnosis", "instruction": "concrete repair"}}
  ],
  "recommendation": "accept|revise|reject"
}}

Distilled style excerpt:
{style_md[:5000]}

Source evidence map (abstract observations only):
{json.dumps(source_evidence or [], ensure_ascii=False)[:6000]}
""".strip()
    return vision_chat_json(system, user, image_paths)


def normalize_validation_report(
    report: dict[str, Any],
    roles: list[str],
    round_number: int,
    min_score: float,
    min_page_score: float,
    require_low_copying_risk: bool = False,
    min_text_accuracy: float | None = None,
) -> dict[str, Any]:
    normalized = dict(report)
    if "aggregate_score" not in normalized and "style_fit_score" in normalized:
        normalized["aggregate_score"] = normalized.get("style_fit_score")
    try:
        aggregate = float(normalized.get("aggregate_score", 0))
    except (TypeError, ValueError):
        aggregate = 0.0
    page_results = normalized.get("page_results")
    if not isinstance(page_results, dict):
        page_results = {}
    missing_roles = [role for role in roles if role not in page_results]
    page_scores: list[float] = []
    readability_scores: list[float] = []
    role_fitness_scores: list[float] = []
    text_accuracy_scores: list[float] = []
    for role in roles:
        result = page_results.get(role, {})
        if not isinstance(result, dict):
            result = {}
        try:
            page_scores.append(float(result.get("fit_score", 0)))
        except (TypeError, ValueError):
            page_scores.append(0.0)
        for field, target in (
            ("readability_score", readability_scores),
            ("role_fitness_score", role_fitness_scores),
        ):
            try:
                target.append(float(result.get(field, 0)))
            except (TypeError, ValueError):
                target.append(0.0)
        if min_text_accuracy is not None:
            try:
                text_accuracy_scores.append(float(result.get("text_accuracy_score", 0)))
            except (TypeError, ValueError):
                text_accuracy_scores.append(0.0)
    copying_risk = str(normalized.get("copying_risk", "medium")).lower()
    recommendation = str(normalized.get("recommendation", "revise")).lower()
    hard_reject = copying_risk == "high" or recommendation == "reject"
    copying_review = require_low_copying_risk and copying_risk != "low"
    passed = (
        not hard_reject
        and not copying_review
        and not missing_roles
        and aggregate >= min_score
        and all(score >= min_page_score for score in page_scores)
        and all(score >= min_page_score for score in readability_scores)
        and all(score >= min_page_score for score in role_fitness_scores)
        and (
            min_text_accuracy is None
            or all(score >= min_text_accuracy for score in text_accuracy_scores)
        )
    )
    normalized.update(
        {
            "round": round_number,
            "roles": roles,
            "aggregate_score": aggregate,
            "minimum_page_score": min(page_scores) if page_scores else 0.0,
            "minimum_readability_score": min(readability_scores) if readability_scores else 0.0,
            "minimum_role_fitness_score": min(role_fitness_scores) if role_fitness_scores else 0.0,
            "minimum_text_accuracy_score": min(text_accuracy_scores) if text_accuracy_scores else None,
            "missing_roles": missing_roles,
            "thresholds": {
                "aggregate_score": min_score,
                "page_fit_score": min_page_score,
                "copying_risk": "low" if require_low_copying_risk else "not-high",
                "text_accuracy_score": min_text_accuracy,
            },
            "gate": "reject" if hard_reject else ("accept" if passed else "revise"),
            "passed": passed,
        }
    )
    return normalized


def _page_fit_scores(report: dict[str, Any], roles: list[str]) -> dict[str, float]:
    page_results = report.get("page_results")
    if not isinstance(page_results, dict):
        page_results = {}
    scores: dict[str, float] = {}
    for role in roles:
        result = page_results.get(role)
        if not isinstance(result, dict):
            scores[role] = 0.0
            continue
        try:
            scores[role] = float(result.get("fit_score", 0))
        except (TypeError, ValueError):
            scores[role] = 0.0
    return scores


def compare_validation_rounds(
    champion: dict[str, Any],
    candidate: dict[str, Any],
    roles: list[str],
    min_score: float,
    min_page_score: float,
    min_improvement: float = 3.0,
    max_regression: float = 2.0,
) -> dict[str, Any]:
    """Decide whether a repaired round is a monotonic improvement."""
    old_scores = _page_fit_scores(champion, roles)
    new_scores = _page_fit_scores(candidate, roles)
    weak_roles = [role for role in roles if old_scores[role] < min_page_score]
    target_roles = weak_roles or roles
    sentinel_roles = [role for role in roles if role not in weak_roles]
    gains = {role: new_scores[role] - old_scores[role] for role in roles}
    copy_rank = {"low": 0, "medium": 1, "high": 2}
    old_copy = str(champion.get("copying_risk", "medium")).lower()
    new_copy = str(candidate.get("copying_risk", "medium")).lower()
    copying_not_worse = copy_rank.get(new_copy, 1) <= copy_rank.get(old_copy, 1)
    target_gain = min((gains[role] for role in target_roles), default=0.0)
    sentinel_regression = max(
        (max(0.0, -gains[role]) for role in sentinel_roles),
        default=0.0,
    )
    try:
        aggregate_gain = float(candidate.get("aggregate_score", 0)) - float(
            champion.get("aggregate_score", 0)
        )
    except (TypeError, ValueError):
        aggregate_gain = -100.0
    if weak_roles:
        target_improved = target_gain >= min_improvement
    else:
        target_improved = aggregate_gain >= min_improvement
    promoted = (
        candidate.get("gate") != "reject"
        and copying_not_worse
        and target_improved
        and sentinel_regression <= max_regression
        and float(candidate.get("aggregate_score", 0)) >= min(
            min_score, float(champion.get("aggregate_score", 0)) - max_regression
        )
    )
    reasons: list[str] = []
    if candidate.get("gate") == "reject":
        reasons.append("candidate hit the hard rejection gate")
    if not copying_not_worse:
        reasons.append(f"copying risk worsened from {old_copy} to {new_copy}")
    if not target_improved:
        reasons.append(
            f"minimum target gain {target_gain:.1f} did not reach {min_improvement:.1f}"
            if weak_roles
            else f"aggregate gain {aggregate_gain:.1f} did not reach {min_improvement:.1f}"
        )
    if sentinel_regression > max_regression:
        reasons.append(
            f"sentinel regression {sentinel_regression:.1f} exceeded {max_regression:.1f}"
        )
    return {
        "promoted": promoted,
        "weak_roles": weak_roles,
        "target_roles": target_roles,
        "sentinel_roles": sentinel_roles,
        "role_gains": gains,
        "minimum_target_gain": target_gain,
        "maximum_sentinel_regression": sentinel_regression,
        "aggregate_gain": aggregate_gain,
        "copying_not_worse": copying_not_worse,
        "reasons": reasons,
    }


def revise_profile(
    manifest: dict[str, Any],
    profile: dict[str, Any],
    report: dict[str, Any],
    validation_images: dict[str, Path],
) -> dict[str, Any]:
    if not (os.getenv("VISION_BASE_URL") and os.getenv("VISION_API_KEY")):
        raise RuntimeError("VISION_BASE_URL/VISION_API_KEY not configured")
    references = [Path(item["path"]) for item in manifest.get("images", [])[:8]]
    generated = [validation_images[role] for role in report.get("roles", []) if role in validation_images]
    system = (
        "You repair a distilled presentation design-system profile from evaluation evidence. "
        "Return one complete revised profile as JSON. Preserve successful rules, fix systemic causes, "
        "and never encode source assets, source copy, or exact source arrangements."
    )
    user = f"""
Revise the profile so the next validation round improves across every page role.
Apply the report's repair_actions and systemic mismatches. Prefer reusable layout grammar and measurable
constraints over vague adjectives. Do not optimize only the weakest page at the cost of deck consistency.

Current profile:
{json.dumps(profile, ensure_ascii=False)[:12000]}

Validation report:
{json.dumps(report, ensure_ascii=False)[:9000]}

Return the complete profile with the same core fields, including design_tokens, identity_anchors,
source_evidence, layout_system, layout_bank, density_rules, variation_rules, anti_repetition_rules,
cover_layout, content_layout, data_layout, section_layout, closing_layout, typography,
image_treatment, iconography, chart_style, forbidden, do_not_copy, scenarios, and provenance_summary.
""".strip()
    return vision_chat_json(system, user, references + generated)


def run_validation_loop(
    manifest: dict[str, Any],
    profile: dict[str, Any],
    style_id: str,
    style_name: str,
    work_dir: Path,
    roles: list[str],
    max_rounds: int,
    min_score: float,
    min_page_score: float,
    auto_revise: bool,
    min_round_improvement: float = 3.0,
    max_role_regression: float = 2.0,
    min_text_accuracy: float = 90.0,
    max_profile_repairs: int = 2,
) -> dict[str, Any]:
    history_dir = work_dir / "evaluations"
    history_dir.mkdir(parents=True, exist_ok=True)
    current_profile = profile
    latest_report: dict[str, Any] = {}
    latest_images: dict[str, Path] = {}
    champion_profile = profile
    champion_report: dict[str, Any] = {}
    champion_images: dict[str, Path] = {}
    champion_round = 0
    rounds_completed = 0
    for round_number in range(1, max_rounds + 1):
        rounds_completed = round_number
        round_dir = history_dir / f"round-{round_number:02d}"
        round_dir.mkdir(parents=True, exist_ok=True)
        style_md = render_style_markdown(
            current_profile,
            style_id,
            style_name,
        )
        layout_sidecar = (
            build_layout_sidecar(current_profile, style_id, manifest_source_hash(manifest))
            if auto_revise
            else None
        )
        (round_dir / "candidate-style.md").write_text(style_md, encoding="utf-8")
        if layout_sidecar:
            (round_dir / "candidate-style.layouts.json").write_text(
                json.dumps(layout_sidecar, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        (round_dir / "profile.json").write_text(
            json.dumps(current_profile, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        try:
            latest_images = generate_validation_deck(
                style_md, style_name, round_dir, roles, layout_sidecar
            )
            raw_report = validate_style_fit(
                manifest,
                style_md,
                latest_images,
                current_profile.get("source_evidence"),
            )
        except Exception as exc:
            latest_report = {
                "round": round_number,
                "roles": roles,
                "gate": "generation-failed",
                "passed": False,
                "error": str(exc),
                "advancement": {
                    "promoted": False,
                    "compared_to_round": champion_round or None,
                    "reasons": ["validation round did not complete"],
                },
            }
            (round_dir / "report.json").write_text(
                json.dumps(latest_report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            if champion_report:
                break
            raise
        if raw_report is None:
            latest_report = {
                "round": round_number,
                "roles": roles,
                "gate": "needs-review",
                "passed": False,
                "status": "images-generated",
                "note": "Vision comparison was unavailable; generated pages require human review.",
            }
        else:
            latest_report = normalize_validation_report(
                raw_report,
                roles,
                round_number,
                min_score,
                min_page_score,
                require_low_copying_risk=auto_revise,
                min_text_accuracy=min_text_accuracy if auto_revise else None,
            )
        if round_number == 1 or not champion_report:
            advancement = {
                "promoted": True,
                "compared_to_round": None,
                "reasons": ["initial validation round establishes the champion"],
            }
        else:
            advancement = compare_validation_rounds(
                champion_report,
                latest_report,
                roles,
                min_score,
                min_page_score,
                min_round_improvement,
                max_role_regression,
            )
            advancement["compared_to_round"] = champion_round
        latest_report["advancement"] = advancement
        if advancement.get("promoted"):
            champion_profile = current_profile
            champion_report = latest_report
            champion_images = latest_images
            champion_round = round_number
        (round_dir / "report.json").write_text(
            json.dumps(latest_report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if advancement.get("promoted") and latest_report.get("gate") == "accept":
            break
        if round_number == 1 and latest_report.get("gate") == "reject":
            break
        if not auto_revise or round_number >= max_rounds or raw_report is None:
            break
        current_profile = ensure_profile_contract(
            manifest,
            revise_profile(
                manifest,
                champion_profile,
                latest_report,
                latest_images,
            ),
            max_profile_repairs,
        )

    selected_report = champion_report or latest_report
    selected_images = champion_images or latest_images
    selected_profile = champion_profile if champion_report else current_profile
    terminal_gate = selected_report.get("gate", "needs-review")
    if terminal_gate == "revise":
        terminal_gate = "needs-review"
    summary = {
        "status": terminal_gate,
        "rounds_completed": rounds_completed,
        "champion_round": champion_round,
        "roles": roles,
        "latest_report": selected_report,
        "last_attempt_report": latest_report,
        "latest_image_dir": str(next(iter(selected_images.values())).parent) if selected_images else "",
        "profile": selected_profile,
        "style_markdown": render_style_markdown(
            selected_profile,
            style_id,
            style_name,
        ),
    }
    (history_dir / "summary.json").write_text(
        json.dumps({key: value for key, value in summary.items() if key not in {"profile", "style_markdown"}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def load_urls(args: argparse.Namespace) -> list[str]:
    urls = list(args.url or [])
    if args.input:
        for line in Path(args.input).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped


def build_manifest(urls: list[str], work_dir: Path, max_images: int, preferred_width: int, delay: float) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    pages: list[dict[str, str]] = []
    remaining = max_images
    for url in urls:
        html = fetch_text(url)
        meta = extract_meta(html, url)
        pages.append(meta)
        selected = select_preview_images(extract_image_candidates(html, url), remaining, preferred_width)
        if not selected:
            raise RuntimeError(f"no preview images found: {url}")
        records.extend(download_images(selected, work_dir / "images", delay))
        remaining = max_images - len(records)
        if remaining <= 0:
            break
        time.sleep(delay)
    return {
        "title": pages[0].get("title", "") if pages else "",
        "description": pages[0].get("description", "") if pages else "",
        "canonical_url": pages[0].get("canonical_url", urls[0]) if pages else urls[0],
        "source_pages": pages,
        "images": records,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score and distill high-quality web PPT template previews.")
    parser.add_argument("--url", action="append", help="Template detail URL. Repeatable.")
    parser.add_argument("--input", help="File with one URL per line.")
    parser.add_argument("--style-id", help="Output style id.")
    parser.add_argument("--name", help="Human-readable style name.")
    parser.add_argument("--styles-dir", default=str(DEFAULT_STYLES_DIR))
    parser.add_argument(
        "--profile-json",
        default="",
        help="Resume validation from an existing complete structured profile JSON.",
    )
    parser.add_argument(
        "--baseline-style",
        default="",
        help=(
            "Existing paired style Markdown to compare against with identical validation cases. "
            "Requires --closed-loop; the candidate is published only after net visual improvement."
        ),
    )
    parser.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR))
    parser.add_argument("--max-images", type=int, default=12)
    parser.add_argument("--preferred-width", type=int, default=1120)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--min-score", type=float, default=78)
    parser.add_argument("--state-db", default=str(DEFAULT_STATE_DB), help="SQLite state database for resume/dedupe/provenance.")
    parser.add_argument("--resume", action="store_true", help="Reuse existing manifest/score/state records when possible.")
    parser.add_argument("--refresh", action="store_true", help="Re-fetch and re-score even if this source URL was seen before.")
    parser.add_argument("--list-state", action="store_true", help="List prior template distillation records and exit.")
    parser.add_argument("--batch-one-per-url", action="store_true", help="Process each input URL as its own independent style.")
    parser.add_argument("--style-prefix", default="", help="Optional prefix for generated style ids in batch mode.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of URLs to process in batch mode.")
    parser.add_argument(
        "--validate-style",
        action="store_true",
        help="Generate one or more validation pages and compare them with the source previews.",
    )
    parser.add_argument(
        "--closed-loop",
        action="store_true",
        help="Run multi-page validation and automatically revise the profile until it passes or reaches the round cap.",
    )
    parser.add_argument(
        "--validation-roles",
        default=None,
        help=(
            f"Comma-separated page roles. Available: {','.join(VALIDATION_SCENARIOS)}. "
            "Defaults to cover for --validate-style and cover,section,content,data for --closed-loop."
        ),
    )
    parser.add_argument(
        "--validation-suite",
        choices=("standard", "generalization"),
        default="standard",
        help=(
            "Validation case set. generalization adds comparison and a held-out "
            "table+timeline data case and routes every case through the production selector."
        ),
    )
    parser.add_argument("--max-validation-rounds", type=int, default=2)
    parser.add_argument(
        "--max-profile-repairs",
        type=int,
        default=2,
        help="Maximum complete-profile structural repairs before paid image validation.",
    )
    parser.add_argument("--min-validation-score", type=float, default=82)
    parser.add_argument("--min-page-score", type=float, default=74)
    parser.add_argument("--min-round-improvement", type=float, default=3)
    parser.add_argument("--max-role-regression", type=float, default=2)
    parser.add_argument("--min-text-accuracy", type=float, default=90)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--score-only", action="store_true")
    parser.add_argument("--force-distill", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def print_state_rows(rows: list[sqlite3.Row]) -> None:
    if not rows:
        print("No state records.")
        return
    for row in rows:
        score = "" if row["total_score"] is None else f"{row['total_score']:.1f}"
        print(
            "\t".join(
                [
                    row["updated_at"] or "",
                    row["status"] or "",
                    row["decision"] or "",
                    score,
                    row["style_id"] or "",
                    row["title"] or "",
                    row["canonical_url"] or "",
                    row["output_style_path"] or row["distill_prompt_path"] or row["error"] or "",
                ]
            )
        )


def load_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def run_batch(args: argparse.Namespace, urls: list[str], state: StateStore, run_id: str) -> int:
    selected_urls = urls[: args.limit] if args.limit and args.limit > 0 else urls
    results: list[dict[str, Any]] = []
    script_path = Path(__file__).resolve()
    for index, url in enumerate(selected_urls, start=1):
        style_seed = Path(urllib.parse.urlparse(url).path).name or f"template-{index:03d}"
        style_id = slugify(f"{args.style_prefix}-{style_seed}" if args.style_prefix else style_seed)
        cmd = [
            sys.executable,
            str(script_path),
            "--url",
            url,
            "--style-id",
            style_id,
            "--styles-dir",
            str(args.styles_dir),
            "--work-dir",
            str(args.work_dir),
            "--state-db",
            str(args.state_db),
            "--max-images",
            str(args.max_images),
            "--preferred-width",
            str(args.preferred_width),
            "--delay",
            str(args.delay),
            "--min-score",
            str(args.min_score),
        ]
        for flag in ["resume", "refresh", "score_only", "force_distill", "overwrite", "validate_style", "closed_loop"]:
            if getattr(args, flag):
                cmd.append(f"--{flag.replace('_', '-')}")
        if args.validation_roles:
            cmd.extend(["--validation-roles", str(args.validation_roles)])
        if args.baseline_style:
            cmd.extend(["--baseline-style", str(args.baseline_style)])
        if args.profile_json:
            cmd.extend(["--profile-json", str(args.profile_json)])
        if args.validation_suite != "standard":
            cmd.extend(["--validation-suite", str(args.validation_suite)])
        cmd.extend(
            [
                "--max-validation-rounds",
                str(args.max_validation_rounds),
                "--max-profile-repairs",
                str(args.max_profile_repairs),
                "--min-validation-score",
                str(args.min_validation_score),
                "--min-page-score",
                str(args.min_page_score),
                "--min-round-improvement",
                str(args.min_round_improvement),
                "--max-role-regression",
                str(args.max_role_regression),
                "--min-text-accuracy",
                str(args.min_text_accuracy),
            ]
        )
        print(f"[{index}/{len(selected_urls)}] {url} -> {style_id}", flush=True)
        proc = subprocess.run(cmd, text=True, capture_output=True)
        if proc.stdout:
            print(proc.stdout.rstrip())
        if proc.stderr:
            print(proc.stderr.rstrip(), file=sys.stderr)
        results.append({"url": url, "style_id": style_id, "returncode": proc.returncode})
        if proc.returncode != 0:
            print(f"Batch item failed: {url}", file=sys.stderr)
    report_path = Path(args.work_dir) / "batch_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    failures = [item for item in results if item["returncode"] != 0]
    print(f"Batch complete: {len(results) - len(failures)} succeeded, {len(failures)} failed")
    print(f"Batch report: {report_path}")
    state.finish_run(run_id, "batch-complete" if not failures else "batch-partial")
    state.close()
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    load_scoped_env_files()
    args = parse_args(argv)
    if args.baseline_style and not args.closed_loop:
        print("error: --baseline-style requires --closed-loop", file=sys.stderr)
        return 2
    state = StateStore(Path(args.state_db))
    if args.list_state:
        print_state_rows(state.list_templates())
        state.close()
        return 0

    run_id = state.begin_run(args)
    urls = load_urls(args)
    if not urls:
        print("error: provide --url or --input", file=sys.stderr)
        state.finish_run(run_id, "failed", "missing url/input")
        state.close()
        return 2

    if args.batch_one_per_url:
        return run_batch(args, urls, state, run_id)

    try:
        first_html = fetch_text(urls[0])
        first_meta = extract_meta(first_html, urls[0])
        style_id = slugify(args.style_id or first_meta["page_slug"])
        style_name = args.name or re.sub(r"\s*\|\s*.*$", "", first_meta.get("title", "")).strip() or style_id
        canonical_url = first_meta.get("canonical_url") or urls[0]

        existing = state.get(canonical_url)
        if args.resume and existing and not args.refresh and not args.force_distill and not args.overwrite:
            existing_status = existing["status"]
            complete_statuses = {
                "prompted",
                "distilled",
                "validated",
                "validation_review",
                "validation_failed",
                "validation_reject",
                "accept",
                "reject",
                "rejected",
                "review",
            }
            if existing_status in complete_statuses:
                print(
                    f"Resumed from state: {existing_status}; "
                    f"score={existing['total_score']}; decision={existing['decision']}"
                )
                print(f"State DB: {state.path}")
                if existing["manifest_path"]:
                    print(f"Manifest: {existing['manifest_path']}")
                if existing["quality_report_path"]:
                    print(f"Quality report: {existing['quality_report_path']}")
                if existing["output_style_path"]:
                    print(f"Style: {existing['output_style_path']}")
                if existing["distill_prompt_path"]:
                    print(f"Distill prompt: {existing['distill_prompt_path']}")
                state.finish_run(run_id, "resumed")
                state.close()
                return 0

        if args.dry_run:
            selected = select_preview_images(extract_image_candidates(first_html, urls[0]), args.max_images, args.preferred_width)
            print(json.dumps([item.__dict__ for item in selected], ensure_ascii=False, indent=2))
            state.finish_run(run_id, "dry-run")
            state.close()
            return 0

        work_dir = Path(args.work_dir) / style_id
        work_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = work_dir / "source_manifest.json"
        quality_path = work_dir / "quality_report.json"

        manifest = None
        if args.resume and not args.refresh:
            manifest = load_json_file(manifest_path)
        if manifest is None:
            partial_manifest = {
                "title": first_meta.get("title", ""),
                "description": first_meta.get("description", ""),
                "canonical_url": canonical_url,
                "source_pages": [first_meta],
                "images": [],
                "style_id": style_id,
                "style_name": style_name,
            }
            state.upsert_template(partial_manifest, "extracting", work_dir)
            manifest = build_manifest(urls, work_dir, args.max_images, args.preferred_width, args.delay)
            manifest.update({"style_id": style_id, "style_name": style_name})
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        canonical_url = manifest.get("canonical_url") or canonical_url
        state.upsert_template(manifest, "manifested", work_dir)
        state.record_images(canonical_url, manifest.get("images", []))

        quality = None
        if args.resume and not args.refresh:
            quality = load_json_file(quality_path)
        if quality is None:
            quality = make_quality_report(manifest, args.min_score)
            quality_path.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
        source_hash = manifest_source_hash(manifest)
        state.update_quality(canonical_url, quality, quality_path, source_hash)

        accepted = quality["decision"] == "accept" and quality["total_score"] >= args.min_score
        if args.score_only or (not accepted and not args.force_distill):
            terminal_status = "scored" if accepted else quality["decision"]
            state.update_status(canonical_url, terminal_status)
            print(f"Score: {quality['total_score']} / 100; decision: {quality['decision']}")
            print(f"Wrote quality report: {quality_path}")
            print(f"Wrote manifest: {manifest_path}")
            print(f"State DB: {state.path}")
            if not accepted:
                print("Skipped distillation because the template did not pass the quality gate.")
            state.finish_run(run_id, terminal_status)
            state.close()
            return 0

        prompt_path = work_dir / "distill_prompt.md"
        if not (os.getenv("VISION_BASE_URL") and os.getenv("VISION_API_KEY")):
            write_manual_prompt(
                prompt_path,
                manifest,
                quality,
                style_id,
                style_name,
                styles_dir=Path(args.styles_dir),
            )
            state.update_status(canonical_url, "prompted", distill_prompt_path=str(prompt_path))
            print(f"Score: {quality['total_score']} / 100; decision: {quality['decision']}")
            print(f"Wrote manual distillation prompt: {prompt_path}")
            print(f"State DB: {state.path}")
            print("VISION_BASE_URL/VISION_API_KEY not set; structured style pair was not auto-generated.")
            state.finish_run(run_id, "prompted")
            state.close()
            return 0

        profile_path = work_dir / "style_profile.json"
        if args.profile_json:
            resume_profile_path = Path(args.profile_json).expanduser().resolve()
            profile = load_json_file(resume_profile_path)
            if profile is None:
                raise FileNotFoundError(f"profile JSON not found: {resume_profile_path}")
            profile = ensure_profile_contract(
                manifest,
                profile,
                max(0, args.max_profile_repairs),
            )
        else:
            profile = distill_profile(
                manifest,
                quality,
                style_id,
                style_name,
                max_profile_repairs=max(0, args.max_profile_repairs),
            )
        output_path = Path(args.styles_dir) / f"{style_id}.md"
        sidecar_path = output_path.with_suffix(".layouts.json")
        existing_outputs = [path for path in (output_path, sidecar_path) if path.exists()]
        if existing_outputs and not args.overwrite:
            existing_text = ", ".join(str(path) for path in existing_outputs)
            print(f"error: style output already exists, pass --overwrite: {existing_text}", file=sys.stderr)
            state.update_status(canonical_url, "failed", error=f"style output exists: {existing_text}")
            state.finish_run(run_id, "failed", f"style output exists: {existing_text}")
            state.close()
            return 3
        status_paths = {
            "style_profile_path": str(profile_path),
        }
        terminal_status = "distilled"
        validate_requested = args.validate_style or args.closed_loop
        if validate_requested:
            validation_report_path = work_dir / "validation_report.json"
            try:
                roles = select_validation_roles(
                    args.validation_roles,
                    args.closed_loop,
                    args.validation_suite,
                )
                validation = run_validation_loop(
                    manifest=manifest,
                    profile=profile,
                    style_id=style_id,
                    style_name=style_name,
                    work_dir=work_dir,
                    roles=roles,
                    max_rounds=max(1, args.max_validation_rounds if args.closed_loop else 1),
                    min_score=args.min_validation_score,
                    min_page_score=args.min_page_score,
                    auto_revise=args.closed_loop,
                    min_round_improvement=args.min_round_improvement,
                    max_role_regression=args.max_role_regression,
                    min_text_accuracy=args.min_text_accuracy,
                    max_profile_repairs=max(0, args.max_profile_repairs),
                )
                if args.baseline_style and validation.get("status") == "accept":
                    baseline_style_path = Path(args.baseline_style).expanduser().resolve()
                    baseline_md, baseline_sidecar = load_style_pair(baseline_style_path)
                    baseline_dir = work_dir / "evaluations" / "baseline"
                    baseline_images = generate_validation_deck(
                        baseline_md,
                        style_name,
                        baseline_dir,
                        roles,
                        baseline_sidecar,
                    )
                    candidate_dir = Path(str(validation.get("latest_image_dir") or ""))
                    candidate_images = {
                        role: candidate_dir / f"{role}.png" for role in roles
                    }
                    missing_candidate_images = [
                        str(path) for path in candidate_images.values() if not path.is_file()
                    ]
                    if missing_candidate_images:
                        raise FileNotFoundError(
                            "candidate champion images missing: "
                            + ", ".join(missing_candidate_images)
                        )
                    raw_comparison = validate_migration_pair(
                        manifest,
                        baseline_images,
                        candidate_images,
                        roles,
                    )
                    comparison = normalize_migration_comparison(
                        raw_comparison,
                        roles,
                        candidate_validation_passed=True,
                        min_improvement=args.min_round_improvement,
                        max_regression=args.max_role_regression,
                        min_text_accuracy=args.min_text_accuracy,
                    )
                    comparison["baseline_style"] = str(baseline_style_path)
                    comparison_path = work_dir / "evaluations" / "migration-comparison.json"
                    comparison_path.write_text(
                        json.dumps(comparison, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    validation["latest_report"]["migration_comparison"] = comparison
                    validation["migration_comparison"] = comparison
                    if not comparison.get("promoted"):
                        validation["status"] = "needs-review"
                profile = validation["profile"]
                style_md = validation["style_markdown"]
                latest_report = validation["latest_report"]
                validation_report_path.write_text(
                    json.dumps(latest_report, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                status_paths["validation_report_path"] = str(validation_report_path)
                status_paths["validation_image_path"] = validation.get("latest_image_dir", "")
                terminal_status = validation_terminal_status(
                    validation["status"], args.closed_loop
                )
                if terminal_status == "validation_reject":
                    status_paths["error"] = "validation rejected staged style"
                elif terminal_status == "validation_review":
                    status_paths["error"] = "validation did not reach the acceptance gate"
            except Exception as exc:
                validation_report_path.write_text(
                    json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                status_paths["validation_report_path"] = str(validation_report_path)
                terminal_status = "validation_failed"
                status_paths["error"] = str(exc)
                style_md = render_style_markdown(
                    profile,
                    style_id,
                    style_name,
                )
        else:
            style_md = render_style_markdown(
                profile,
                style_id,
                style_name,
            )

        profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        review_candidate_path: Path | None = None
        if terminal_status == "validation_reject":
            for rejected_path in (output_path, sidecar_path):
                try:
                    rejected_path.unlink()
                except FileNotFoundError:
                    pass
            status_paths["output_style_path"] = ""
        elif args.closed_loop and terminal_status != "validated":
            for unpublished_path in (output_path, sidecar_path):
                try:
                    unpublished_path.unlink()
                except FileNotFoundError:
                    pass
            review_candidate_path = work_dir / "review-candidate.md"
            write_style_pair(
                review_candidate_path,
                style_md,
                profile,
                style_id,
                source_hash,
            )
            status_paths["output_style_path"] = str(review_candidate_path)
        else:
            write_style_pair(output_path, style_md, profile, style_id, source_hash)
            status_paths["output_style_path"] = str(output_path)

        state.update_status(canonical_url, terminal_status, **status_paths)
        print(f"Score: {quality['total_score']} / 100; decision: {quality['decision']}")
        if terminal_status == "validation_reject":
            print("Closed-loop validation rejected the style; no staged style was kept.")
        elif review_candidate_path is not None:
            print(f"Validation did not pass; kept review candidate only: {review_candidate_path}")
        else:
            print(f"Wrote style: {output_path}")
            print(f"Wrote layout sidecar: {sidecar_path}")
        if validate_requested:
            print(f"Validation report: {work_dir / 'validation_report.json'}")
        print(f"State DB: {state.path}")
        state.finish_run(run_id, terminal_status, status_paths.get("error", ""))
        state.close()
        return 0
    except Exception as exc:
        try:
            state.finish_run(run_id, "failed", str(exc))
        finally:
            state.close()
        raise


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
