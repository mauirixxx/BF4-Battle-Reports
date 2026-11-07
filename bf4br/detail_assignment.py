"""Pure v2 opt-in role translation; no database or process side effects.

A historical or rotating node becomes a detail node only with explicit v2
activation. Daily assignments are never converted.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class DetailRole:
    role: str
    platform: int | None


def v2_assignment(assignment, enabled=False):
    if not assignment:
        return None
    role,platform=assignment
    if role=='daily':
        if platform not in (1,32,64):
            raise ValueError('daily platform invalid')
        return DetailRole('daily',platform)
    if role=='detail':
        if platform is not None:
            raise ValueError('detail role must be platform flexible')
        return DetailRole('detail',None)
    if role in ('historical','rotating'):
        if (role=='rotating' and platform is not None) or (role=='historical' and platform not in (1,32,64)):
            raise ValueError('legacy assignment invalid')
        if enabled:
            return DetailRole('detail',None)
        return DetailRole(role,platform)
    raise ValueError('unknown assignment role')


def detail_worker_module(assignment,enabled=False):
    mapped=v2_assignment(assignment,enabled)
    if mapped is None:
        return None
    if mapped.role=='detail':
        return 'bf4br.detail_worker'
    if mapped.role=='daily':
        return 'bf4br.daily_persona_worker'
    return 'bf4br.persona_worker'
