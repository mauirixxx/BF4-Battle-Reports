"""Pure supervisor assignment reconciliation helpers (v1.0.6 opt-in)."""
from dataclasses import dataclass

@dataclass(frozen=True)
class WorkerSpec:
    kind: str
    role: str
    platform: int | None


def desired_persona_specs(assignment, persona_target):
    """Only a single persona process per node is centrally assigned for now.

    No assignment means no persona process in centrally managed mode. This is
    fail-closed, unlike the legacy supervisor's fallback to platform PC.
    """
    if not assignment or persona_target <= 0:
        return []
    role, platform = assignment
    if role not in ('daily', 'historical', 'rotating'):
        raise ValueError('invalid assignment role')
    if (role == 'rotating' and platform is not None) or (role != 'rotating' and platform not in (1,32,64)):
        raise ValueError('invalid assignment platform')
    if persona_target != 1:
        raise ValueError('central scheduling requires exactly one persona worker per node')
    return [WorkerSpec('persona', role, platform)]


def changed(current, desired):
    """Return only specs requiring drain and replacement."""
    return current != desired
