import argparse
import json
from pathlib import Path


def execute(spec):
    from app.quality.sandbox import configure_environment,ModelBudget,safe
    from app.quality.test_model_profile import configure_test_model
    configure_environment();configure_test_model()
    from app.core.config import settings
    from app.agent.model import create_chat_model
    from app.quality.agent_evaluation import judge
    settings.cloud_max_tokens=min(settings.cloud_max_tokens,2200)
    settings.cloud_timeout_seconds=50
    budget=ModelBudget(2,spec['max_tokens']);restore=budget.install()
    try:
        result=judge(spec['evaluation_snapshot'],create_chat_model())
        result['model']=settings.cloud_model
    except Exception as exc: result={'status':'blocked','error':safe(type(exc).__name__+': '+str(exc)),'raw_response':safe(getattr(exc,'response',None))}
    finally: restore()
    if budget.calls<=0 and result.get('status')=='completed': result={'status':'blocked','error':'独立模型未产生可计量HTTP调用'}
    return {**result,'budget':budget.output()}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--request');parser.add_argument('--output');args=parser.parse_args()
    Path(args.output).write_text(json.dumps(execute(json.loads(Path(args.request).read_text(encoding='utf-8'))),ensure_ascii=False),encoding='utf-8')
