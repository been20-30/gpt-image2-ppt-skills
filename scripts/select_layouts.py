#!/usr/bin/env python3
"""Assign varied Arabic art-direction families to a compatible slides plan."""
from __future__ import annotations
import argparse, json
from pathlib import Path

SEQUENCE = ["hero", "editorial", "framework", "timeline", "comparison", "big_number", "quote", "closing"]
TYPE_HINT = {"cover":"hero", "agenda":"framework", "section":"editorial", "data":"big_number", "quote":"quote", "closing":"closing"}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("input"); ap.add_argument("output"); args=ap.parse_args()
    src=Path(args.input); dst=Path(args.output); plan=json.loads(src.read_text(encoding="utf-8")); slides=plan.get("slides", [])
    if isinstance(slides, dict): slides=list(slides.values())
    used=[]
    for i, slide in enumerate(slides):
        requested=slide.get("layout_family") or slide.get("composition_family") or TYPE_HINT.get(slide.get("page_type"))
        family=requested if requested in SEQUENCE else SEQUENCE[i % len(SEQUENCE)]
        if used and family == used[-1]:
            family=next((x for x in SEQUENCE if x != used[-1]), "editorial")
        slide["layout_family"]=family; slide["story_role"]={"hero":"establish","editorial":"frame","framework":"explain","timeline":"sequence","comparison":"contrast","big_number":"emphasize","quote":"humanize","closing":"land"}.get(family,"explain")
        slide["layout_signature"]=f"{family}:rtl-text-first"
        used.append(family)
    plan["language"] = plan.get("language", "ar")
    plan["direction"] = "rtl" if str(plan["language"]).lower().startswith("ar") else plan.get("direction", "ltr")
    plan["layout_sequence"] = used
    plan["layout_policy"] = {"no_adjacent_repeat": True, "max_card_ratio": 0.33, "text_first": True}
    dst.parent.mkdir(parents=True, exist_ok=True); dst.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"output":str(dst),"slides":len(slides),"layout_sequence":used},ensure_ascii=False))

if __name__ == "__main__": main()
