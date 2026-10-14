import uuid
import re

from app.agent.fallback import fallback_reply
from app.agent.guard import execute_tool
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.context import current
from app.agent.intent import classify
from app.agent.rate_limit import check_rate
from app.core.config import settings
from app.core.logging import logger
from app.services.session import SessionService, compact_messages


class ModelOutputError(RuntimeError):
    pass


def message_text(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text") or ""))
        return "".join(parts)
    return str(content or "")


def run_tool_loop(history: list[dict], summary: str, user_text: str, llm=None, max_steps: int | None = None):
    """模型选出工具后，一律走 guard.execute_tool，不把模型参数直接送进数据库。"""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

    from app.agent.tools import langchain_tools

    tools = langchain_tools(classify(user_text))
    if llm is None:
        from langchain_ollama import ChatOllama

        llm = ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0,
            reasoning=settings.ollama_reasoning,
            num_ctx=settings.ollama_num_ctx,
            num_predict=settings.ollama_num_predict,
            client_kwargs={"timeout": settings.ollama_timeout_seconds},
        )
        if tools:
            llm = llm.bind_tools(tools)
    elif tools and hasattr(llm, "bind_tools"):
        llm = llm.bind_tools(tools)

    actor = current()[1]
    messages = [SystemMessage(content=SYSTEM_PROMPT + f"\n当前身份：{actor.role}。商家可查本店全部订单和经营概览，买家只能查本人订单。工具仅支持查询，写操作请引导至业务页面。")]
    if summary:
        messages.append(SystemMessage(content=f"此前对话摘要：{summary}"))
    for item in history:
        if item.get("role") == "user":
            messages.append(HumanMessage(content=item.get("content") or ""))
        elif item.get("role") == "assistant":
            messages.append(AIMessage(content=item.get("content") or ""))
    messages.append(HumanMessage(content=user_text))

    traces: list[dict] = []
    steps = max_steps or settings.agent_max_steps
    for step in range(steps):
        ai = llm.invoke(messages)
        calls = getattr(ai, "tool_calls", None) or []
        if not calls:
            text = message_text(ai).strip()
            if not text:
                raise ModelOutputError("模型输出为空")
            return text, traces
        messages.append(ai)
        for index, call in enumerate(calls):
            if index >= 5:
                raise ModelOutputError("单轮工具调用过多")
            name = call.get("name") or ""
            args = call.get("args") or {}
            result = execute_tool(name, args)
            traces.append({"tool": name, "args": args if isinstance(args, dict) else {}, "result": result})
            messages.append(
                ToolMessage(content=result, tool_call_id=call.get("id") or f"call-{step}-{index}")
            )
    return "我查了几轮还没有形成明确答复。请换个说法，或直接告诉我商品名、订单号。", traces


class Assistant:
    def __init__(self) -> None:
        self.sessions = SessionService()

    def chat(self, *, user_id: int, shop_id: int, session_id: str | None, message: str, llm=None) -> dict:
        check_rate(user_id)
        session_id = session_id or uuid.uuid4().hex
        actor = current()[1]
        actor.session_id = session_id
        actor.products.clear()
        state = self.sessions.load(user_id, shop_id, session_id)
        summary_llm = llm
        if summary_llm is None and settings.agent_mode != "fallback":
            try:
                from langchain_ollama import ChatOllama
                summary_llm = ChatOllama(model=settings.ollama_model, base_url=settings.ollama_base_url, temperature=0, reasoning=settings.ollama_reasoning, num_ctx=settings.ollama_num_ctx, num_predict=settings.ollama_num_predict, client_kwargs={"timeout": settings.ollama_timeout_seconds})
            except ImportError:
                summary_llm = None
        state, notice = compact_messages(state, settings.session_max_chars, summary_llm)
        notices = [notice] if notice else []
        intent = classify(message)
        query = message
        if intent == "order" and not re.search(r"PS\d{8,}", message.upper()) and any(word in message for word in ("这个", "它", "刚才")):
            previous = state["summary"] + " " + " ".join(item.get("content", "") for item in state["messages"])
            numbers = re.findall(r"PS\d{8,}", previous.upper())
            if numbers:
                query += " " + numbers[-1]
        if intent == "inventory" and any(word in message for word in ("它", "这个", "刚才")):
            previous_queries = [item["content"] for item in state["messages"] if item.get("role") == "user" and classify(item["content"]) == "product_search"]
            if previous_queries:
                query = previous_queries[-1]
        if settings.agent_mode == "fallback":
            answer, traces = fallback_reply(query)
            mode = "fallback"
        else:
            try:
                answer, traces = run_tool_loop(state["messages"], state["summary"], query, llm=llm)
                if intent != "unclear" and not traces:
                    raise ModelOutputError("业务查询未调用数据工具")
                mode = "llm"
            except Exception as exc:
                logger.warning("大模型不可用，改用规则兜底：%s", exc)
                answer, traces = fallback_reply(query)
                mode = "fallback"
                notices.append("模型暂时不可用，已使用规则查询回复")
        state["messages"] = list(state["messages"]) + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": answer},
        ]
        state, notice_after = compact_messages(state, settings.session_max_chars, summary_llm)
        if notice_after and notice_after not in notices:
            notices.append(notice_after)
        self.sessions.save(user_id, shop_id, session_id, state)
        return {
            "session_id": session_id,
            "answer": answer,
            "mode": mode,
            "tools": traces,
            "notices": notices,
            "intent": intent if intent != "unclear" or mode == "fallback" else "model_routed",
            "products": list({row["id"]: row for row in actor.products}.values()),
        }

    def read_session(self, user_id: int, shop_id: int, session_id: str) -> dict:
        state = self.sessions.load(user_id, shop_id, session_id)
        return {"session_id": session_id, "summary": state["summary"], "messages": state["messages"]}


assistant = Assistant()
