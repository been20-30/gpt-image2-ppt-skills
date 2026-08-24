#!/usr/bin/env python3
"""Executable Presentation + Design Intelligence for the image-first pipeline."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

ROLES=['hook','context','problem','insight','framework','process','comparison','case_study','data','exercise','summary','closing']
STRATEGIES={
 'hook':('hero','typography-led'), 'context':('editorial','editorial composition'), 'problem':('comparison','contrast composition'),
 'insight':('big_number','typography-led'), 'framework':('framework','diagram'), 'process':('timeline','timeline'),
 'comparison':('comparison','comparison'), 'case_study':('case_study','editorial composition'), 'data':('big_number','big number'),
 'exercise':('process','workshop diagram'), 'summary':('checklist','checklist'), 'closing':('closing','hero visual')}

def classify(slide, index, total):
    text=' '.join(str(slide.get(k,'')) for k in ('title','content','notes')).lower()
    explicit=str(slide.get('story_role','')).lower()
    if explicit in ROLES: return explicit
    if index==0 or slide.get('page_type')=='cover': return 'hook'
    if index==total-1 or slide.get('page_type')=='closing': return 'closing'
    if any(x in text for x in ['مقارنة','versus','مقابل','comparison']): return 'comparison'
    if any(x in text for x in ['خطوات','عملية','مرحلة','process','timeline']): return 'process'
    if any(x in text for x in ['إطار','نموذج','framework']): return 'framework'
    if any(x in text for x in ['رقم','نسبة','بيانات','data','%']): return 'data'
    if any(x in text for x in ['مشكلة','تحدي','problem']): return 'problem'
    if any(x in text for x in ['خلاصة','ملخص','summary']): return 'summary'
    return 'context' if index==1 else 'insight'

def density(text):
    n=len(re.sub(r'\s+',' ',text).strip())
    return 'sparse' if n<100 else 'moderate' if n<260 else 'dense'

def typography(audience, style, role, d):
    display='Noto Kufi Arabic' if role in {'hook','closing','insight','data'} else 'IBM Plex Sans Arabic'
    body='IBM Plex Sans Arabic'; latin='IBM Plex Sans'; numeric='IBM Plex Sans'
    title=40 if d=='sparse' else 34 if d=='moderate' else 28
    body_size=20 if d=='sparse' else 17 if d=='moderate' else 14
    if role=='data': title=max(title,36)
    return {'display_font':display,'body_font':body,'latin_font':latin,'numeric_font':numeric,'title_weight':800 if role in {'hook','closing'} else 700,'body_weight':500,'title_size_pt':title,'body_size_pt':body_size,'line_height':1.25 if d=='dense' else 1.35,'letter_spacing':'0' if display.endswith('Arabic') else '-0.01em','text_width':'42%' if d=='dense' else '58%' if d=='moderate' else '68%','direction':'rtl','safe_zone':'8%'}

def plan_intelligently(plan):
    slides=plan.get('slides',[]); total=len(slides); prev=None; cards=0; decisions=[]
    audience=plan.get('audience','professional'); style=plan.get('style',plan.get('recommended_style',''))
    for i,s in enumerate(slides):
        text=str(s.get('content',''))
        role=classify(s,i,total); d=density(text); family,strategy=STRATEGIES[role]
        penalty=[]
        if prev==family:
            penalty.append('adjacent_layout_repetition'); alternatives=[v[0] for r,v in STRATEGIES.items() if v[0]!=family and v[0]!=prev]; family=alternatives[i%len(alternatives)]
        if family in {'framework','comparison','checklist'}: cards+=1
        if cards/max(1,i+1)>.34 and family in {'framework','comparison','checklist'}:
            penalty.append('card_overuse'); family='editorial' if role not in {'data','process'} else 'big_number'
        typo=typography(audience,style,role,d)
        s.update({'story_role':role,'content_density':d,'visual_strategy':strategy,'layout_family':family,'composition':f'{family}: {strategy}, text-first, RTL safe zone','typography_decision':typo,'intelligence_penalties':penalty,'generation_instruction':f'Use {family} composition for a {role} slide; preserve RTL and the protected {typo["safe_zone"]} text zone.'})
        prev=family; decisions.append({'slide_number':s.get('slide_number',i+1),'story_role':role,'content_density':d,'visual_strategy':strategy,'layout_family':family,'penalties':penalty})
    plan['presentation_intelligence']={'version':'1.0.0','audience':audience,'direction':'rtl' if str(plan.get('language','')).startswith('ar') else 'ltr','pipeline':['content_analysis','story_planning','visual_strategy','typography_decision','layout_allocation','prompt_compilation'],'decisions':decisions}
    return plan

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('input'); ap.add_argument('output'); a=ap.parse_args(); plan=json.loads(Path(a.input).read_text(encoding='utf-8')); Path(a.output).parent.mkdir(parents=True,exist_ok=True); Path(a.output).write_text(json.dumps(plan_intelligently(plan),ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(plan['presentation_intelligence'],ensure_ascii=False))
if __name__=='__main__': main()
