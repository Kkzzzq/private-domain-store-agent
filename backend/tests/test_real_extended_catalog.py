from collections import Counter
from app.quality.real_cases import cases,doc_for


def test_extended_real_catalog_has_76_distinct_executable_cases_and_chinese_documents():
    rows=cases()
    assert len(rows)==len({r['id'] for r in rows})==76
    assert Counter(r['adapter'] for r in rows)=={'real_shop_api':40,'real_shop_agent':16,'real_shop_browser':20}
    for row in rows:
        doc=doc_for(row['id']);assert doc['steps'] and doc['expected']
        assert doc['code_file'].endswith('.py')
