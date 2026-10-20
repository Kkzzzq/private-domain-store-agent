"""用例文档：执行步骤、预期结果与对应代码入口。

文案按用例族拆在四个数据文件里（A 两批、F、E），这里只做合并与兜底。
刻意不把文案塞进 `catalog.cases()`：用例指纹（CATALOG_VERSION）只跟执行定义有关，
改文案不应该让已批准的计划失效。
"""
from importlib import import_module

from app.quality.catalog import case_by_id


SOURCES = ("case_docs_assistant_a", "case_docs_assistant_b", "case_docs_functional", "case_docs_browser", "case_docs_op")

ADAPTER_FILES = {
    "isolated_assistant_api": "backend/app/quality/case_runner.py::execute",
    "registered_pytest": "backend/app/quality/case_runner.py::execute",
    "registered_browser": "backend/app/quality/browser.py::execute_browser",
    "declarative_assistant": "backend/app/quality/case_versions.py::execute_definition",
}

RISKS = {"read-only", "writes"}


def _load():
    docs = {}
    for module in SOURCES:
        try:
            loaded = import_module("app.quality." + module).DOCS
        except ModuleNotFoundError:
            continue
        docs.update(loaded)
    return docs


CASE_DOCS = _load()


def doc_for(case_id):
    """返回该用例的步骤/预期/代码入口；没有登记文案时给结构化兜底，绝不返回空壳。"""
    row = case_by_id(case_id) or {}
    doc = CASE_DOCS.get(case_id) or {}
    risk = doc.get("risk") if doc.get("risk") in RISKS else "read-only"
    return {
        "steps": list(doc.get("steps") or ["执行已登记用例：" + str(row.get("title") or case_id)]),
        "expected": list(doc.get("expected") or ["用例返回通过，且隔离清理确认成功"]),
        "code_file": doc.get("code_file") or ADAPTER_FILES.get(row.get("adapter"), "backend/app/quality/case_runner.py"),
        "code_node": doc.get("code_node") or row.get("adapter") or "execute",
        "risk": risk,
    }


def documented_ids():
    return sorted(CASE_DOCS)


def missing_docs(case_ids):
    """哪些用例还没有人工登记的步骤/预期文案（供回归测试与运维核对）。"""
    return [case_id for case_id in case_ids if case_id not in CASE_DOCS or not CASE_DOCS[case_id].get("steps") or not CASE_DOCS[case_id].get("expected")]