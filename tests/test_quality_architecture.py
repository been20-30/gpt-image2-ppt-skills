import json
import tempfile
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
int_spec=importlib.util.spec_from_file_location('pi', ROOT/'scripts/presentation_intelligence.py')
pi=importlib.util.module_from_spec(int_spec); int_spec.loader.exec_module(pi)
spec=importlib.util.spec_from_file_location('qe', ROOT/'scripts/quality_engine.py')
qe=importlib.util.module_from_spec(spec); spec.loader.exec_module(qe)


def plan(families, language='ar'):
    return {'language':language,'direction':'rtl','slides':[{'slide_number':i+1,'content':'عنوان عربي واضح\nنص مختصر للاختبار','layout_family':f,'story_role':'explain'} for i,f in enumerate(families)]}


def test_story_intelligence_emits_executable_decision_chain():
    result=pi.plan_intelligently({'language':'ar','audience':'executive','slides':[{'slide_number':1,'content':'المشكلة هي بطء القرار ونحتاج إلى إطار واضح.'},{'slide_number':2,'content':'ثلاث خطوات عملية لتحسين القرار.'}]})
    first=result['slides'][0]
    assert first['story_role'] in {'hook','problem'}
    for key in ['intent','argument','information_type','audience_need','content_density','visual_strategy','visual_focal_point','information_flow','visual_metaphor','image_strategy','text_strategy','composition_balance','typography_decision','generation_instruction']:
        assert key in first and first[key] is not None, key
    assert result['presentation_intelligence']['pipeline'][-1]=='prompt_compilation'


def test_typography_is_configuration_driven():
    config=pi.load_config(); original=config['typography']['font_pairs']['arabic_editorial']['body']; config['typography']['font_pairs']['arabic_editorial']['body']='Test Arabic Body'; result=pi.plan_intelligently({'language':'ar','slides':[{'content':'نص تجريبي طويل بما يكفي للاختبار.'}]},config); assert result['slides'][0]['typography_decision']['body_font']=='Test Arabic Body'; config['typography']['font_pairs']['arabic_editorial']['body']=original


def test_design_engine_rejects_adjacent_repetition():
    result=qe.design_quality(plan(['hero','hero']), {})
    assert result['passed'] is False
    assert 'repeated_layout' in result['hard_failures']


def test_design_engine_accepts_varied_story():
    result=qe.design_quality(plan(['hero','editorial','framework','timeline','closing']), {})
    assert result['passed'] is True
    assert result['score'] >= 80


def test_technical_engine_is_independent_from_design():
    with tempfile.TemporaryDirectory() as d:
        out=Path(d); (out/'libreoffice').mkdir()
        from PIL import Image
        for i in range(2): Image.new('RGB',(1600,900),(30,30,30)).save(out/'libreoffice'/f'slide-{i+1}.png')
        tech=qe.technical_quality(plan(['hero','hero']), out, {})
        design=qe.design_quality(plan(['hero','hero']), {})
        assert tech['passed'] is True
        assert design['passed'] is False


def test_premium_acceptance_requires_design_and_technical_pass():
    import json, subprocess, sys
    with tempfile.TemporaryDirectory() as d:
        out=Path(d); (out/'libreoffice').mkdir()
        from PIL import Image
        for i in range(2): Image.new('RGB',(1600,900),(30,30,30)).save(out/'libreoffice'/f'slide-{i+1}.png')
        bad={'language':'ar','direction':'rtl','slides':[{'content':'x','layout_family':'hero'},{'content':'x','layout_family':'hero'}]}
        plan_path=out/'bad.json'; plan_path.write_text(json.dumps(bad),encoding='utf-8')
        report=out/'report.json'; cmd=[sys.executable,str(ROOT/'scripts/quality_engine.py'),'--plan',str(plan_path),'--output',str(out),'--design-system',str(ROOT/'design_system/intelligence_config.json'),'--report',str(report)]
        cp=subprocess.run(cmd,capture_output=True,text=True)
        assert cp.returncode==2
        p=json.loads(report.read_text()); assert p['technical_pass'] is True; assert p['design_pass'] is False; assert p['premium_pass'] is False


def test_technical_engine_rejects_missing_rtl():
    with tempfile.TemporaryDirectory() as d:
        result=qe.technical_quality({'language':'en','direction':'ltr','slides':[{'content':'x'}]}, Path(d), {})
        assert result['passed'] is False
        assert 'rtl_not_declared' in result['hard_failures']


def test_visual_critic_emits_render_evidence():
    with tempfile.TemporaryDirectory() as d:
        out=Path(d); (out/'libreoffice').mkdir()
        from PIL import Image, ImageDraw
        im=Image.new('RGB',(1600,900),(20,20,20)); ImageDraw.Draw(im).rectangle((100,100,900,500),fill=(230,230,230)); im.save(out/'libreoffice'/'slide-1.png')
        import importlib.util
        spec=importlib.util.spec_from_file_location('dc',ROOT/'scripts/design_critic.py'); dc=importlib.util.module_from_spec(spec); spec.loader.exec_module(dc)
        result=dc.visual_critic(out, {'slides':[{'content':'x'}]})
        assert result['rendered_slides']==1 and result['evidence'][0]['non_background_ratio']>0


def test_technical_engine_counts_renders_and_lo_verification():
    with tempfile.TemporaryDirectory() as d:
        out=Path(d); (out/'libreoffice').mkdir()
        from PIL import Image
        Image.new('RGB',(1600,900),(30,30,30)).save(out/'libreoffice'/'slide-1.png')
        result=qe.technical_quality(plan(['hero']), out, {})
        assert result['renders_found']==1
        assert result['libreoffice_verification'] is True

if __name__=='__main__':
    tests=[v for k,v in globals().items() if k.startswith('test_')]
    for t in tests: t(); print(f'PASS {t.__name__}')
