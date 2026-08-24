#!/usr/bin/env python3
"""Data-driven Design Knowledge resolver used by the existing Intelligence pipeline."""
from __future__ import annotations
import argparse, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/'design_knowledge'
REQUIRED={'id','description','applicability','constraints','recommendations','selection_signals','relationships','priority','confidence'}

def load_knowledge(root=None):
    root=Path(root) if root else ROOT; entities=[]; errors=[]
    files=sorted(root.rglob('*.json'))
    for f in files:
        if f.name in {'knowledge_entity.schema.json','manifest.json'}: continue
        try:
            data=json.loads(f.read_text(encoding='utf-8')); values=data.get('entities',[data]) if isinstance(data,dict) else []
            for e in values:
                missing=sorted(REQUIRED-set(e));
                if missing: errors.append({'file':str(f),'missing':missing})
                else: entities.append(e)
        except Exception as exc: errors.append({'file':str(f),'error':str(exc)})
    return {'entities':entities,'errors':errors,'root':str(root)}

def _matches(value, wanted):
    vals=value if isinstance(value,list) else [value]; return any(str(w).lower() in {str(x).lower() for x in vals} for w in (wanted if isinstance(wanted,list) else [wanted]))

def resolve(context, root=None):
    kb=load_knowledge(root); q={k:str(v).lower() for k,v in context.items() if v is not None}; scored=[]
    for e in kb['entities']:
        score=0; matched=[]
        signals=e.get('selection_signals',{})
        for k,v in q.items():
            if k in signals and _matches(signals[k],v): score+=2; matched.append(k)
            elif k in e.get('applicability',[]) or v in [str(x).lower() for x in e.get('applicability',[])]: score+=1; matched.append(k)
        if score: scored.append((score*float(e.get('priority',0.5))*float(e.get('confidence',0.5)),e,matched))
    scored.sort(key=lambda x:x[0],reverse=True); selected=[{'entity':e,'score':round(s,3),'matched':m} for s,e,m in scored]
    selected_ids={x['entity']['id'] for x in selected}
    for e in kb['entities']:
        if ('repair' in e.get('relationships',{}) or e['id'].endswith('_anti_pattern') or e['id']=='three_equal_cards') and e['id'] not in selected_ids:
            selected.append({'entity':e,'score':round(float(e.get('priority',0.5))*0.5,3),'matched':['default_guardrail']})
    return {'context':context,'schema_valid':not kb['errors'],'validation_errors':kb['errors'],'selected':selected,'bundle':{'audience':None,'purpose':None,'style':None,'typography':None,'composition':None,'imagery':None,'layout':None,'anti_patterns':[]}}

def knowledge_bundle(context, root=None):
    r=resolve(context,root); b=r['bundle']
    for item in r['selected']:
        e=item['entity']; rid=e['id']; rel=e.get('relationships',{})
        if rid in {'professional','executive','academic','student'}: b['audience']=e
        if rid in {'analysis','workshop','launch','teaching'}: b['purpose']=e
        if 'style' in rel and b['style'] is None: b['style']=e
        if rid.startswith('arabic_') or 'typography' in rel: b['typography']=e
        if 'composition' in rel or rid in {'framework','timeline','comparison'}: b['composition']=e
        if 'imagery' in rel or rid=='evidence-led': b['imagery']=e
        if 'repair' in rel or rid=='three_equal_cards': b['anti_patterns'].append(e)
        if 'layout' in rel: b['layout']=e
    return {'knowledge_version':'5.0.0','schema_valid':r['schema_valid'],'validation_errors':r['validation_errors'],'selected':r['selected'][:12],'bundle':b}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--context',required=True); ap.add_argument('--output',required=True); ap.add_argument('--root'); a=ap.parse_args(); context=json.loads(Path(a.context).read_text(encoding='utf-8')); result=knowledge_bundle(context,a.root); Path(a.output).parent.mkdir(parents=True,exist_ok=True); Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps({'schema_valid':result['schema_valid'],'selected':len(result['selected']),'output':a.output},ensure_ascii=False)); raise SystemExit(0 if result['schema_valid'] else 2)
if __name__=='__main__': main()
