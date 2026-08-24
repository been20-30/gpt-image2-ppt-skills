#!/usr/bin/env python3
"""Data-driven style selection for the existing image-first generation engine."""
from __future__ import annotations
import argparse, json
from pathlib import Path

DEFAULT=Path(__file__).resolve().parents[1]/'design_system/style_profiles.json'

def load_profiles(path=None):
    p=Path(path) if path else DEFAULT
    return json.loads(p.read_text(encoding='utf-8'))

def select_style(topic='', audience='professional', purpose='teaching', tone='clear', content_type='mixed', requested_style='', profiles=None, knowledge=None):
    data=profiles or load_profiles(); items=data['profiles']; selection=data.get('selection',{}); scores={k:0 for k in items}; text=f'{topic} {content_type} {tone}'.lower()
    if requested_style in items: scores[requested_style]+=100
    if knowledge:
        for selected in knowledge.get('selected',[]):
            for candidate in selected.get('entity',{}).get('relationships',{}).get('style',[]):
                if candidate in scores: scores[candidate]+=8

    for kw, names in selection.get('topic_keywords',{}).items():
        if kw in text:
            for n in names: scores[n]+=4
    for n in selection.get('audience_bias',{}).get(audience,[]): scores[n]+=3
    for n in selection.get('purpose_bias',{}).get(purpose,[]): scores[n]+=3
    if 'sparse' in text:
        for n,p in items.items(): scores[n]+=2 if p.get('density')=='sparse' else 0
    if 'data' in text or content_type in {'data','analysis'}:
        for n,p in items.items(): scores[n]+=2 if 'data' in p.get('acceptable_layout_families',[]) or p.get('composition','').find('grid')>=0 else 0
    chosen=max(scores,key=scores.get) if scores else selection.get('default','clean-tech-blue')
    profile=dict(items[chosen]); profile.update({'id':chosen,'selection_score':scores[chosen],'selection_evidence':{'topic':topic,'audience':audience,'purpose':purpose,'tone':tone,'content_type':content_type,'requested_style':requested_style},'ranked_candidates':sorted(scores.items(),key=lambda x:x[1],reverse=True)})
    return profile

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--topic',default=''); ap.add_argument('--audience',default='professional'); ap.add_argument('--purpose',default='teaching'); ap.add_argument('--tone',default='clear'); ap.add_argument('--content-type',default='mixed'); ap.add_argument('--requested-style',default=''); ap.add_argument('--output',required=True); ap.add_argument('--knowledge'); a=ap.parse_args(); out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True); knowledge=json.loads(Path(a.knowledge).read_text(encoding='utf-8')) if a.knowledge else None; out.write_text(json.dumps(select_style(a.topic,a.audience,a.purpose,a.tone,a.content_type,a.requested_style,knowledge=knowledge),ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps({'style':json.loads(out.read_text())['id'],'output':str(out)},ensure_ascii=False))
if __name__=='__main__': main()
