import uuid

from app.agent.fallback import fallback_reply
from app.agent.guard import execute_tool
from app.agent.prompts import SYSTEM_PROMPT
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

    tools = langchain_tools()
    if llm is None:
        from langchain_ollama import ChatOllama

        llm = ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0,
        ).bind_tools(tools)
    elif hasattr(llm, "bind_tools"):
        llm = llm.bind_tools(tools)

    messages = [SystemMessage(content=SYSTEM_PROMPT)]
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
        session_id = session_id or uuid.uuid4().hex
        state = self.sessions.load(user_id, shop_id, session_id)
        state, notice = compact_messages(state, settings.session_max_chars)
        notices = [notice] if notice else []
        if settings.agent_mode == "fallback":
            answer, traces = fallback_reply(message)
            mode = "fallback"
        else:
            try:
                answer, traces = run_tool_loop(state["messages"], state["summary"], message, llm=llm)
                mode = "llm"
            except Exception as exc:
                if settings.agent_mode == "llm":
                    raise
                logger.warning("大模型不可用，改用规则兜底：%s", exc)
                answer, traces = fallback_reply(message)
                mode = "fallback"
        state["messages"] = list(state["messages"]) + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": answer},
        ]
        state, notice_after = compact_messages(state, settings.session_max_chars)
        if notice_after and notice_after not in notices:
            notices.append(notice_after)
        self.sessions.save(user_id, shop_id, session_id, state)
        return {
            "session_id": session_id,
            "answer": answer,
            "mode": mode,
            "tools": traces,
            "notices": notices,
        }

    def read_session(self, user_id: int, shop_id: int, session_id: str) -> dict:
        state = self.sessions.load(user_id, shop_id, session_id)
        return {"session_id": session_id, "summary": state["summary"], "messages": state["messages"]}


assistant = Assistant()
