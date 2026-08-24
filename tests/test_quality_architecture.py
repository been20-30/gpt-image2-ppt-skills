import json
import tempfile
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('qe', ROOT/'scripts/quality_engine.py')
qe=importlib.util.module_from_spec(spec); spec.loader.exec_module(qe)


def plan(families, language='ar'):
    return {'language':language,'direction':'rtl','slides':[{'slide_number':i+1,'content':'عنوان عربي واضح\nنص مختصر للاختبار','layout_family':f,'story_role':'explain'} for i,f in enumerate(families)]}


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


def test_technical_engine_rejects_missing_rtl():
    with tempfile.TemporaryDirectory() as d:
        result=qe.technical_quality({'language':'en','direction':'ltr','slides':[{'content':'x'}]}, Path(d), {})
        assert result['passed'] is False
        assert 'rtl_not_declared' in result['hard_failures']


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
