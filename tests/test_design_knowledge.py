import json, importlib.util, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name,file):
 s=importlib.util.spec_from_file_location(name,ROOT/file); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
k=load('k','scripts/design_knowledge.py'); si=load('si','scripts/style_intelligence.py'); pi=load('pi','scripts/presentation_intelligence.py')

def test_knowledge_schema_loads():
 r=k.load_knowledge(); assert r['errors']==[]; assert len(r['entities'])>=8

def test_audience_and_purpose_affect_resolution():
 a=k.knowledge_bundle({'audience':'professional','purpose':'analysis','industry':'technology'})
 b=k.knowledge_bundle({'audience':'professional','purpose':'workshop','industry':'technology'})
 assert a['selected'] and b['selected']
 assert a['bundle']['purpose']['id'] != b['bundle']['purpose']['id']

def test_recipe_selects_style_relationship():
 r=k.knowledge_bundle({'audience':'teachers','purpose':'workshop','tone':'warm','content_type':'mixed'})
 style=si.select_style(topic='education',audience='professional',purpose='teaching',knowledge=r)
 assert style['id'] in {'geometric-duotone-thesis','editorial-mono','clean-tech-blue'}

def test_knowledge_changes_prompt_fields():
 kb=k.knowledge_bundle({'audience':'professional','purpose':'analysis','industry':'technology'})
 plan={'language':'ar','intelligence_mode':True,'style_profile':{},'design_knowledge':kb,'slides':[{'content':'تحليل نظام تقني'}]}
 result=pi.plan_intelligently(plan)
 s=result['slides'][0]; assert s['information_type']; assert s['visual_strategy']; assert s['typography_decision']

def test_antipattern_is_resolved_and_exposed():
 r=k.knowledge_bundle({'audience':'professional','purpose':'analysis'})
 assert any(x['entity']['id']=='three_equal_cards' for x in r['selected'])

def test_new_entity_can_be_added_without_python_change():
 with tempfile.TemporaryDirectory() as d:
  root=Path(d); (root/'new.json').write_text(json.dumps({'id':'new_style','description':'x','applicability':['test'],'constraints':['x'],'recommendations':['x'],'forbidden_patterns':[],'selection_signals':{'audience':['test']},'relationships':{'style':['clean-tech-blue']},'priority':1,'confidence':1,'data':{} }))
  r=k.knowledge_bundle({'audience':'test'},root); assert any(x['entity']['id']=='new_style' for x in r['selected'])

def test_missing_knowledge_falls_back():
 r=k.knowledge_bundle({'audience':'unknown'},'/tmp/empty-knowledge-root')
 assert r['schema_valid'] and r['selected']==[]

if __name__=='__main__':
 for name,fn in sorted(globals().items()):
  if name.startswith('test_'): fn(); print('PASS',name)
