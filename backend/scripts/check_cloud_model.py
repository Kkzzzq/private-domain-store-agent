import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from app.core.config import Settings, settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--report", default="data/acceptance/cloud-smoke.json")
    args = parser.parse_args()
    configured = Settings(_env_file=args.env_file)
    if configured.model_provider != "cloud":
        parser.error("需要MODEL_PROVIDER=cloud")
    for name in Settings.model_fields:
        setattr(settings, name, getattr(configured, name))
    from app.agent.model import create_chat_model
    report = {"at": datetime.now(timezone.utc).isoformat(), "model": settings.cloud_model,
              "scope": "real_model_protocol_with_synthetic_tool_result_not_database_or_rag_acceptance", "cases": []}
    try:
        model = create_chat_model()
        answer = model.invoke([HumanMessage(content="请只回复：连接成功")])
        if not answer.content:
            raise ValueError("模型输出为空")
        report["cases"].append({"name": "real_chat", "passed": True, "answer": answer.content,
                                "actual_model": answer.response_metadata.get("model")})
        tool = {"type": "function", "function": {"name": "search_knowledge", "description": "查询本店售后政策，售后问题必须先查询此工具。",
                "parameters": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}}}
        bound = model.bind_tools([tool])
        messages = [SystemMessage(content="你是店铺售后助手。售后问题必须先调用search_knowledge，拿到证据再回答。"),
                    HumanMessage(content="签收以后退货期限有几天？")]
        first = bound.invoke(messages)
        if not first.tool_calls or first.tool_calls[0]["name"] != "search_knowledge":
            raise ValueError("没有原生工具调用")
        call = first.tool_calls[0]
        if not isinstance(call["args"].get("question"), str) or not call["args"]["question"].strip():
            raise ValueError("缺少工具参数")
        final = bound.invoke(messages + [first, ToolMessage(content="[合成测试数据，非真实Chroma检索] 店铺政策：签收后7天内支持无理由退货，定制商品不适用。来源：after_sales.md。", tool_call_id=call["id"])])
        if not any(word in final.content for word in ("7", "七")):
            raise ValueError("回答与合成工具结果不符")
        report["cases"].append({"name": "native_tool_roundtrip", "passed": True, "tool": call["name"], "args": call["args"], "answer": final.content,
                                "actual_models": [first.response_metadata.get("model"), final.response_metadata.get("model")]})
        report["passed"] = True
    except Exception as error:
        report["passed"] = False
        report["error_type"] = type(error).__name__
        status = re.search(r"HTTP (\d{3})", str(error))
        if status:
            report["http_status"] = int(status.group(1))
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
