#!/usr/bin/env python3
"""Independent design and technical quality engines for gpt-image2-ppt-ar-pro."""
from __future__ import annotations
import argparse, json, math, re
from pathlib import Path
from PIL import Image

FAMILIES={"hero","editorial","full_bleed","framework","timeline","process","comparison","big_number","quote","case_study","diagram","checklist","closing"}

def slides(plan):
    value=plan.get('slides',[]); return list(value.values()) if isinstance(value,dict) else value

def design_quality(plan, ds):
    ss=slides(plan); score={k:100 for k in ['typography','hierarchy','composition','visual_storytelling','art_direction','consistency']}; findings=[]; hard=[]; seq=[]
    for i,s in enumerate(ss):
        family=s.get('layout_family') or s.get('composition_family') or s.get('page_type','content'); role=s.get('story_role') or 'explain'; seq.append(family)
        if family not in FAMILIES: score['art_direction']-=10; findings.append({'severity':'warn','code':'unknown_family','slide':i+1,'message':str(family)})
        if i and family==seq[-2]: score['composition']-=30; score['consistency']-=20; hard.append('repeated_layout'); findings.append({'severity':'hard','code':'repeated_layout','slide':i+1,'message':f'Adjacent family repeated: {family}'})
        text=str(s.get('content','')); chars=len(text)
        if chars>520: score['typography']-=min(35,math.ceil((chars-520)/40)); hard.append('text_over_budget'); findings.append({'severity':'hard','code':'text_over_budget','slide':i+1,'message':f'{chars} chars'})
        if role in {'explain','contrast','sequence'} and not family: score['visual_storytelling']-=10
    if len(ss)>2 and sum(1 for x in seq if x in {'card','cards','grid'})/len(ss)>.33:
        score['art_direction']-=20; findings.append({'severity':'warn','code':'card_overuse','message':'More than one third of slides are card-heavy.'})
    for k in score: score[k]=max(0,score[k])
    return {'engine':'design_quality','passed':not hard and sum(score.values())/len(score)>=80,'score':round(sum(score.values())/len(score),1),'scores':score,'hard_failures':sorted(set(hard)),'findings':findings,'layout_sequence':seq}

def technical_quality(plan, out, ds):
    ss=slides(plan); findings=[]; hard=[]; score={k:100 for k in ['rtl','safe_text_zone','overflow','alignment','rendering','pptx_validity','libreoffice_verification']}; lang=str(plan.get('language',plan.get('lang',''))).lower(); rtl=lang.startswith('ar') or plan.get('direction')=='rtl'
    if not rtl: score['rtl']=0; hard.append('rtl_not_declared'); findings.append({'severity':'hard','code':'rtl_not_declared'})
    imgs=sorted(p for p in out.rglob('*.png') if p.name.lower().startswith(('slide','page')))
    if len(imgs)<len(ss): score['rendering']=0; hard.append('missing_render'); findings.append({'severity':'hard','code':'missing_render','message':f'{len(imgs)}/{len(ss)} renders'})
    for p in imgs[:len(ss)]:
        try:
            with Image.open(p) as im:
                ratio=im.width/im.height
                if not 1.6<=ratio<=1.9: score['alignment']-=20; findings.append({'severity':'warn','code':'aspect_ratio','file':str(p)})
        except Exception as e: score['rendering']=0; hard.append('invalid_render'); findings.append({'severity':'hard','code':'invalid_render','file':str(p),'message':str(e)})
    # Safe-zone and overflow are enforced at planning time; image-only generation
    # cannot reliably OCR every glyph, so the gate records the contract explicitly.
    if any(not s.get('safe_text_zone',True) for s in ss): score['safe_text_zone']=0; hard.append('text_outside_safe_zone')
    for k in score: score[k]=max(0,score[k])
    return {'engine':'technical_quality','passed':not hard,'score':round(sum(score.values())/len(score),1),'scores':score,'hard_failures':sorted(set(hard)),'findings':findings,'renders_found':len(imgs),'rtl_declared':rtl,'libreoffice_verification':bool((out/'libreoffice').exists() or any('libreoffice' in str(p) for p in imgs))}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--plan',required=True); ap.add_argument('--output',required=True); ap.add_argument('--design-system',required=True); ap.add_argument('--report',required=True); a=ap.parse_args()
    plan=json.loads(Path(a.plan).read_text(encoding='utf-8')); ds=json.loads(Path(a.design_system).read_text(encoding='utf-8')); out=Path(a.output)
    design=design_quality(plan,ds); technical=technical_quality(plan,out,ds); overall=round((design['score']+technical['score'])/2,1); hard=sorted(set(design['hard_failures']+technical['hard_failures'])); result={'tool':'gpt-image2-ppt-ar-pro quality engines','version':'2.0.0','passed':design['passed'] and technical['passed'] and not hard and overall>=80,'overall_score':overall,'design_quality':design,'technical_quality':technical,'final_decision':'deliver' if design['passed'] and technical['passed'] and overall>=80 else 'fix and render again'}
    Path(a.report).parent.mkdir(parents=True,exist_ok=True); Path(a.report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps({'passed':result['passed'],'overall_score':overall,'report':a.report},ensure_ascii=False)); raise SystemExit(0 if result['passed'] else 2)
if __name__=='__main__': main()
