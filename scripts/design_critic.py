#!/usr/bin/env python3
"""Actionable structural and rendered-slide critics."""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageStat

def structural_critic(result):
    repairs=[]
    for f in result.get('findings',[]):
        code=f.get('code'); slide=f.get('slide')
        if code=='repeated_layout': repairs.append({'slide':slide,'problem':'Layout repetition detected','evidence':f.get('message'),'cause':'Adjacent slides share a composition family.','severity':'high','recommended_change':'Replace the repeated family with a framework, timeline, comparison, or editorial composition.','regeneration_strategy':'select_layout(framework_or_editorial); regenerate without adjacent reuse.'})
        elif code=='card_overuse': repairs.append({'slide':slide,'problem':'Card overuse detected','evidence':f.get('message'),'cause':'The deck uses modular containers instead of a visual argument.','severity':'medium','recommended_change':'Replace cards with a diagram, timeline, or single visual metaphor.','regeneration_strategy':'select_layout(diagram_or_timeline); regenerate without default cards.'})
        elif code=='text_over_budget': repairs.append({'slide':slide,'problem':'Typography budget exceeded','evidence':f.get('message'),'cause':'Too much copy for the selected density and safe zone.','severity':'high','recommended_change':'Reduce to one insight and up to three supporting points, or split the slide.','regeneration_strategy':'regenerate with sparse copy and larger Arabic type.'})
    return {'critic':'structural','repairs':repairs,'repair_count':len(repairs),'next_action':'regenerate' if repairs else 'accept'}

def visual_critic(output_dir, plan):
    files=sorted(Path(output_dir).rglob('*.png')); findings=[]; evidence=[]
    for i,p in enumerate(files[:len(plan.get('slides',[]))],1):
        try:
            im=Image.open(p).convert('RGB').resize((80,45)); stat=ImageStat.Stat(im); spread=max(stat.mean)-min(stat.mean); pixels=list(im.getdata()); bg=pixels[0]; changed=sum(1 for px in pixels if sum(abs(px[j]-bg[j]) for j in range(3))>45)/len(pixels)
            ev={'slide':i,'file':str(p),'luminance_spread':round(spread,2),'non_background_ratio':round(changed,3)}; evidence.append(ev)
            if changed<0.012: findings.append({'slide':i,'problem':'Weak visual focal point','evidence':ev,'cause':'Rendered image is nearly uniform relative to its background.','severity':'medium','recommended_change':'Introduce one dominant visual anchor or typographic statement.','regeneration_strategy':'regenerate with a single focal point and stronger scale contrast.'})
            elif changed>0.82: findings.append({'slide':i,'problem':'Visual noise / weak hierarchy','evidence':ev,'cause':'Too much of the canvas has equal visual activity.','severity':'medium','recommended_change':'Reduce competing decoration and preserve a clear reading path.','regeneration_strategy':'regenerate with one focal region and 30–50% quiet space.'})
        except Exception as exc: findings.append({'slide':i,'problem':'Render could not be analyzed','evidence':str(exc),'cause':'Unreadable or unsupported image.','severity':'high','recommended_change':'Re-render the slide.','regeneration_strategy':'render again before visual inspection.'})
    return {'critic':'visual','rendered_slides':len(evidence),'evidence':evidence,'findings':findings,'repair_count':len(findings),'next_action':'regenerate' if findings else 'accept'}

def critic_from_design(result):
    return structural_critic(result)
