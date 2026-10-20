import asyncio
import json
from threading import BoundedSemaphore, Event
from time import perf_counter

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.agent.assistant import assistant
from app.agent.context import Actor, reset_actor, set_actor
from app.db.session import SessionLocal
from app.schemas.dto import ChatOut


_slots = BoundedSemaphore(8)


def chat_stream(user, shop_id, body):
    identity = (user.id, user.actor_role, user.username)

    async def events():
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        stopped = Event()
        started = perf_counter()

        def emit(event):
            if stopped.is_set():
                raise asyncio.CancelledError()
            event["elapsed_ms"] = round((perf_counter() - started) * 1000)
            loop.call_soon_threadsafe(queue.put_nowait, event)

        def run():
            if not _slots.acquire(blocking=False):
                emit({"type": "error", "status": 429, "detail": "助手当前较忙，请稍后再试"})
                return
            try:
                process()
            except asyncio.CancelledError:
                pass
            except Exception:
                emit({"type": "error", "status": 503, "detail": "助手服务暂时不可用，请稍后重试"})
            finally:
                _slots.release()

        def process():
            with SessionLocal() as db:
                actor = Actor(identity[0], identity[1], identity[2], shop_id, progress=emit)
                token = set_actor(db, actor)
                try:
                    data = assistant.chat(user_id=identity[0], shop_id=shop_id,
                                          session_id=body.session_id, message=body.message.strip())
                    emit({"type": "result", "data": ChatOut.model_validate(data).model_dump()})
                except asyncio.CancelledError:
                    pass
                except HTTPException as exc:
                    emit({"type": "error", "status": exc.status_code, "detail": exc.detail})
                except Exception:
                    emit({"type": "error", "status": 503, "detail": "助手处理失败，请稍后重试"})
                finally:
                    reset_actor(token)

        task = asyncio.create_task(asyncio.to_thread(run))
        try:
            yield json.dumps({"type": "progress", "stage": "accepted", "elapsed_ms": 0}) + "\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10)
                except asyncio.TimeoutError:
                    event = {"type": "heartbeat", "elapsed_ms": round((perf_counter() - started) * 1000)}
                yield json.dumps(event, ensure_ascii=False) + "\n"
                if event["type"] in ("result", "error"):
                    break
        finally:
            stopped.set()
            if task.done():
                task.result()

    return StreamingResponse(events(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
