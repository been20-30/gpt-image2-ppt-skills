#!/usr/bin/env python3
"""Executable Presentation + Design Intelligence for the image-first pipeline."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

DEFAULT_CONFIG=Path(__file__).resolve().parents[1]/'design_system/intelligence_config.json'
ROLES=['hook','context','problem','insight','framework','process','comparison','case_study','data','exercise','summary','closing']

def load_config(path=None):
    candidate=Path(path) if path else DEFAULT_CONFIG
    return json.loads(candidate.read_text(encoding='utf-8')) if candidate.exists() else {}

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

def typography(audience, style, role, d, config=None):
    config=config or load_config(); typ=config.get('typography',{}); pairs=typ.get('font_pairs',{}); roles=typ.get('roles',{}); densities=typ.get('density',{})
    pair=pairs.get(roles.get(role,roles.get('default','arabic_formal')), pairs.get('arabic_formal',{})); scale=densities.get(d,{}); aud=config.get('audiences',{}).get(audience,{})
    title=max(18, int(scale.get('title',34))+int(aud.get('title_size_delta',0))); body=int(scale.get('body',17))
    return {'display_font':pair.get('display'),'body_font':pair.get('body'),'latin_font':pair.get('latin'),'numeric_font':pair.get('numeric'),'title_weight':typ.get('weights',{}).get('display',800),'body_weight':typ.get('weights',{}).get('body',500),'title_size_pt':title,'body_size_pt':body,'line_height':scale.get('line_height',1.3),'letter_spacing':'0','text_width':aud.get('text_width','58%'),'direction':'rtl','safe_zone':typ.get('safe_zone','8%')}

def plan_intelligently(plan, config=None):
    config=config or load_config(); role_config=config.get('story_roles',{}); strategies=config.get('visual_strategy',{}); layout_prefs=config.get('layout_preferences',{});
    slides=plan.get('slides',[]); total=len(slides); prev=None; cards=0; decisions=[]
    audience=plan.get('audience','professional'); style=plan.get('style',plan.get('recommended_style',''))
    for i,s in enumerate(slides):
        text=str(s.get('content',''))
        role=classify(s,i,total); d=density(text); role_spec=role_config.get(role,{}); strategy=role_spec.get('visual_strategy',STRATEGIES.get(role,('editorial','editorial composition'))[1]); family=strategy if strategy in layout_prefs.get('families',[]) else STRATEGIES.get(role,('editorial','editorial composition'))[0]
        penalty=[]
        if prev==family:
            penalty.append('adjacent_layout_repetition'); alternatives=[v[0] for r,v in STRATEGIES.items() if v[0]!=family and v[0]!=prev]; family=alternatives[i%len(alternatives)]
        if family in {'framework','comparison','checklist'}: cards+=1
        if cards/max(1,i+1)>.34 and family in {'framework','comparison','checklist'}:
            penalty.append('card_overuse'); family='editorial' if role not in {'data','process'} else 'big_number'
        typo=typography(audience,style,role,d,config)
        visual=strategies.get(strategy,{})
        s.update({'story_role':role,'intent':s.get('intent',role_spec.get('need','inform')),'argument':s.get('argument',text[:180]),'information_type':s.get('information_type',role_spec.get('information_types',['claim'])[0]),'audience_need':s.get('audience_need',role_spec.get('need','understanding')),'content_density':d,'visual_strategy':strategy,'visual_focal_point':visual.get('focal_point'),'information_flow':visual.get('flow'),'visual_metaphor':visual.get('metaphor'),'image_strategy':visual.get('image'),'text_strategy':visual.get('text'),'composition_balance':visual.get('balance'),'layout_family':family,'composition':f'{family}: {strategy}, text-first, RTL safe zone','typography_decision':typo,'intelligence_penalties':penalty,'generation_instruction':f'Use {family} composition for a {role} slide; preserve RTL and the protected {typo["safe_zone"]} text zone.'})
        prev=family; decisions.append({'slide_number':s.get('slide_number',i+1),'story_role':role,'content_density':d,'visual_strategy':strategy,'layout_family':family,'penalties':penalty})
    plan['presentation_intelligence']={'version':'1.0.0','audience':audience,'direction':'rtl' if str(plan.get('language','')).startswith('ar') else 'ltr','pipeline':['content_analysis','story_planning','visual_strategy','typography_decision','layout_allocation','prompt_compilation'],'decisions':decisions}
    return plan

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('input'); ap.add_argument('output'); ap.add_argument('--config'); a=ap.parse_args(); plan=json.loads(Path(a.input).read_text(encoding='utf-8')); Path(a.output).parent.mkdir(parents=True,exist_ok=True); Path(a.output).write_text(json.dumps(plan_intelligently(plan,load_config(a.config)),ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(plan['presentation_intelligence'],ensure_ascii=False))
if __name__=='__main__': main()
