"""Redact credentials without silently clipping a transcript's nesting or messages."""
from app.quality.sandbox import safe


def redact(value,depth=0):
    if depth>50: raise ValueError('证据嵌套超出上限，无法按完整记录评分')
    if isinstance(value,dict):
        out={}
        metrics={'tokens','max_tokens','total_tokens','input_tokens','output_tokens'}
        for key,item in value.items():
            name=str(key)
            secret=name.lower() not in metrics and any(t in name.lower() for t in ('password','token','authorization','secret','api_key','phone','address','receiver'))
            out[name]='[已脱敏]' if secret else redact(item,depth+1)
        return out
    if isinstance(value,(list,tuple)):return [redact(v,depth+1) for v in value]
    if isinstance(value,str):
        if len(value)>16000:raise ValueError('单条证据过长，不能静默截断完整会话')
        return safe(value)
    return value
