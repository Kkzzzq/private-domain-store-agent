"""Reuse the exact B/support validators and services under an explicit OP shop scope.

No merchant token is issued and no global dependency override is modified.
"""
import inspect
from urllib.parse import unquote
from functools import wraps
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.params import Depends as DependsParam
from fastapi.responses import Response
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from app.api.op_api import require_operator
from app.core.config import settings
from app.core.deps import get_db, get_current_user, require_merchant
from app.db.session import SessionLocal
from app.models.tables import Shop, User
from app.models.governance import WorkspaceAction

router = APIRouter()


def scoped_owner(shop_id: int, request: Request, actual: User = Depends(require_operator), db: Session = Depends(get_db)):
    shop = db.get(Shop, shop_id)
    if shop is None:
        raise HTTPException(404, '店铺不存在')
    owner = db.get(User, shop.merchant_id)
    owner._actor_role = 'merchant'
    owner._op_operator_id = actual.id
    request.state.op_operator_id = actual.id
    request.state.op_shop_id = shop.id
    return owner


def delegate(endpoint):
    signature = inspect.signature(endpoint)
    params = []
    for p in signature.parameters.values():
        if isinstance(p.default, DependsParam) and p.default.dependency in (require_merchant, get_current_user):
            p = p.replace(default=Depends(scoped_owner))
        params.append(p)
    params.append(inspect.Parameter('_op_request', inspect.Parameter.KEYWORD_ONLY, annotation=Request))

    @wraps(endpoint)
    async def wrapped(**kwargs):
        request = kwargs.pop('_op_request')
        write = request.method not in ('GET', 'HEAD', 'OPTIONS')
        action_id = None
        if write:
            reason = unquote(request.headers.get('X-OP-Reason', '')).strip()
            if not 2 <= len(reason) <= 200:
                raise HTTPException(422, '请填写2—200字的平台操作原因')
            # Record intent before invoking existing services, whose transactions
            # can commit or roll back independently (e.g. decoration revision lock).
            with SessionLocal() as log_db:
                action = WorkspaceAction(operator_id=request.state.op_operator_id, shop_id=request.state.op_shop_id,
                    method=request.method, resource=request.url.path[:300], reason=reason)
                log_db.add(action); log_db.commit(); action_id = action.id
        outcome = 'failed'
        try:
            result = await endpoint(**kwargs) if inspect.iscoroutinefunction(endpoint) else await run_in_threadpool(endpoint, **kwargs)
            outcome = 'succeeded'
            return result
        finally:
            if action_id:
                with SessionLocal() as log_db:
                    action = log_db.get(WorkspaceAction, action_id)
                    action.status = outcome
                    log_db.commit()

    wrapped.__signature__ = signature.replace(parameters=params)
    return wrapped


def add_routes(source, exclude=()):
    for route in source.routes:
        if not isinstance(route, APIRoute) or any(route.path == path for path in exclude):
            continue
        router.add_api_route('/shops/{shop_id}' + route.path, delegate(route.endpoint), methods=list(route.methods),
            dependencies=[Depends(scoped_owner)],
            response_model=route.response_model, status_code=route.status_code, tags=['op-workspace'],
            name='op_workspace_' + route.name)


from app.api.b_api import router as business_router
from app.api.support import router as support_router
from app.api.agent_actions import router as agent_router
add_routes(business_router)
add_routes(agent_router)
add_routes(support_router, exclude=('/support/shops/{code}/conversation', '/support/orders/{number}/after-sale'))


@router.get('/workspace/assets/{asset}', include_in_schema=False)
def workspace_asset(asset: str):
    if asset not in ('b.js', 'support-ui.js'):
        raise HTTPException(404, '资源不存在')
    # Same editor, separate session key. Auth/paths are scoped by the bootstrap.
    content = (settings.web_dir / asset).read_text(encoding='utf-8-sig').replace('token_b', 'token_op')
    return Response(content, media_type='application/javascript', headers={'Cache-Control':'no-cache'})
