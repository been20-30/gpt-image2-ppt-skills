#!/usr/bin/env python3
"""Arabic presentation quality gate for gpt-image2-ppt.

This is a conservative gate: it never replaces human visual review, but makes
hard failures and repeatable checks explicit before a deck is delivered.
"""
from __future__ import annotations
import argparse, json, math, re
from pathlib import Path
from PIL import Image, ImageStat

HARD_FAILS = {"missing_render", "low_contrast_proxy", "repeated_layout", "rtl_not_declared", "text_over_budget"}

def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def get_slides(plan):
    slides = plan.get("slides", [])
    if isinstance(slides, dict):
        return list(slides.values())
    return slides

def text_len(slide):
    return len(str(slide.get("content", "")))

def luminance(rgb):
    vals=[]
    for c in rgb:
        v=c/255
        vals.append(v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4)
    return .2126*vals[0]+.7152*vals[1]+.0722*vals[2]

def contrast_proxy(im):
    # Mean channel spread is misleading for dark editorial decks. Use robust
    # luminance percentiles so sparse bright Arabic type is still detected.
    small=im.convert("RGB").resize((64,36))
    values=sorted(luminance(px) for px in small.getdata())
    lo=values[max(0, int(len(values)*0.05))]
    hi=values[min(len(values)-1, int(len(values)*0.95))]
    return (hi-lo)*255

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--output", required=True, help="generation output directory")
    ap.add_argument("--design-system", default=None)
    ap.add_argument("--report", required=True)
    args=ap.parse_args()
    plan_path=Path(args.plan); out=Path(args.output); report_path=Path(args.report)
    plan=load_json(plan_path)
    slides=get_slides(plan)
    ds=load_json(Path(args.design_system)) if args.design_system else {}
    findings=[]; scores={"typography":100,"hierarchy":100,"composition":100,"contrast":100,"spacing":100,"rtl":100,"consistency":100,"visual_impact":100,"storytelling":100}
    hard=[]
    lang=str(plan.get("language", plan.get("lang", ""))).lower()
    rtl = lang.startswith("ar") or plan.get("direction") == "rtl"
    if not rtl:
        scores["rtl"]-=35; hard.append("rtl_not_declared"); findings.append({"severity":"hard","code":"rtl_not_declared","message":"Arabic deck must declare language ar and direction rtl."})
    limit=int(ds.get("safe_text_zone",{}).get("max_chars_per_slide", 520)) if ds else 520
    seen=[]
    image_paths=sorted([p for p in out.rglob("*.png") if p.name.lower().startswith(("slide", "page"))]) if out.exists() else []
    if not image_paths:
        hard.append("missing_render"); findings.append({"severity":"hard","code":"missing_render","message":"No rendered PNG slide found."})
    if len(image_paths) < len(slides):
        hard.append("missing_render"); findings.append({"severity":"hard","code":"missing_render","message":f"Found {len(image_paths)} rendered slides for {len(slides)} planned slides."})
    for i,slide in enumerate(slides):
        n=slide.get("slide_number", i+1); chars=text_len(slide); layout=slide.get("layout_family") or slide.get("composition_family") or slide.get("layout_id") or slide.get("layout") or slide.get("page_type") or "unspecified"; seen.append(str(layout))
        if chars > limit:
            scores["typography"]-=min(20, math.ceil((chars-limit)/80)); hard.append("text_over_budget"); findings.append({"severity":"hard","slide":n,"code":"text_over_budget","message":f"Slide has {chars} characters; budget is {limit}."})
        if i and str(layout)==seen[-2]:
            scores["composition"]-=12; scores["consistency"]-=8; hard.append("repeated_layout"); findings.append({"severity":"hard","slide":n,"code":"repeated_layout","message":f"Layout '{layout}' repeats on adjacent slides."})
    for p in image_paths[:len(slides)]:
        try:
            with Image.open(p) as im:
                if im.width/im.height < 1.6 or im.width/im.height > 1.9:
                    scores["composition"]-=10; findings.append({"severity":"warn","file":str(p),"code":"aspect_ratio","message":"Rendered slide is not close to 16:9."})
                proxy=contrast_proxy(im)
                if proxy < 1.5:
                    scores["contrast"]-=35; hard.append("low_contrast_proxy"); findings.append({"severity":"hard","file":str(p),"code":"low_contrast_proxy","message":"Rendered slide is nearly uniform; regenerate."})
                elif proxy < 8:
                    scores["contrast"]-=8; findings.append({"severity":"warn","file":str(p),"code":"contrast_proxy","message":"Low global luminance spread; verify text contrast visually."})
        except Exception as exc:
            findings.append({"severity":"warn","file":str(p),"code":"image_read","message":str(exc)})
    for key in scores: scores[key]=max(0,min(100,scores[key]))
    overall=round(sum(scores.values())/len(scores),1)
    hard=sorted(set(hard)); passed=not hard and overall >= float(ds.get("quality_gate",{}).get("minimum_score",80))
    report={"tool":"gpt-image2-ppt-ar-pro quality_gate","version":"1.0.0","passed":passed,"overall_score":overall,"scores":scores,"hard_failures":hard,"findings":findings,"slides_checked":len(slides),"renders_found":len(image_paths),"rtl_declared":rtl,"layout_sequence":seen,"recommendation":"deliver" if passed else "fix and render again"}
    report_path.parent.mkdir(parents=True,exist_ok=True); report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"passed":passed,"overall_score":overall,"hard_failures":hard,"report":str(report_path)},ensure_ascii=False))
    raise SystemExit(0 if passed else 2)

if __name__ == "__main__": main()
