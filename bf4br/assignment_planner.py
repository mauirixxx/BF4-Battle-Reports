"""Side-effect-free BF4BR fleet planner, preserving assignments across failures."""
from dataclasses import dataclass
from collections import Counter

PLATFORMS = (1, 32, 64)

@dataclass(frozen=True)
class Assignment:
    node: str
    role: str
    platform: int | None


def plan(nodes, *, capacity=10, previous=()):
    """Keep healthy existing roles; fill missing daily coverage before history.

    Previous assignments are advisory. Only healthy nodes can be assigned.
    A failed rotator is not replaced by displacing a working historical node.
    """
    names=sorted(set(nodes))
    if any(not isinstance(n,str) or not n.strip() for n in names):
        raise ValueError('node names must be nonempty strings')
    if not 0 <= capacity <= 10:
        raise ValueError('capacity must be between 0 and 10')
    names=names[:capacity]
    valid=set(names)
    existing={a.node:a for a in previous if a.node in valid and
              a.role in ('daily','historical','rotating') and
              ((a.role=='rotating' and a.platform is None) or
               (a.role!='rotating' and a.platform in PLATFORMS))}
    result={}
    # Keep exactly one incumbent daily collector for each platform.
    for platform in PLATFORMS:
        candidates=sorted((a for a in existing.values() if a.role=='daily' and a.platform==platform),key=lambda a:a.node)
        if candidates:
            result[candidates[0].node]=candidates[0]
    # Restore daily coverage with minimum reassignment, preferring unassigned nodes.
    for platform in PLATFORMS:
        if any(a.role=='daily' and a.platform==platform for a in result.values()):
            continue
        free=[n for n in names if n not in result and n not in existing]
        if not free:
            free=[n for n in names if n not in result and existing[n].role=='rotating']
        if not free:
            counts=Counter(a.platform for a in existing.values() if a.role=='historical' and a.node not in result)
            free=sorted((n for n in names if n not in result and existing[n].role=='historical'),
                        key=lambda n:(-counts[existing[n].platform],n))
        if free:
            result[free[0]]=Assignment(free[0],'daily',platform)
    # Preserve remaining historical workers; keep at most one rotator.
    for n in names:
        if n in result:
            continue
        a=existing.get(n)
        if a and a.role=='historical':
            result[n]=a
    rotators=[n for n in names if n not in result and existing.get(n) and existing[n].role=='rotating']
    if rotators:
        n=rotators[0]
        result[n]=existing[n]
    free=[n for n in names if n not in result]
    historical=Counter(a.platform for a in result.values() if a.role=='historical')
    for index,n in enumerate(free):
        # The tenth node is flexible, but don't reshuffle existing workers to create it.
        if len(result)==9 and not any(a.role=='rotating' for a in result.values()):
            result[n]=Assignment(n,'rotating',None)
        else:
            platform=min(PLATFORMS,key=lambda p:(historical[p],PLATFORMS.index(p)))
            result[n]=Assignment(n,'historical',platform)
            historical[platform]+=1
    return [result[n] for n in names if n in result]


def next_platform(previous):
    if previous is None:
        return PLATFORMS[0]
    if previous not in PLATFORMS:
        raise ValueError('unsupported platform')
    return PLATFORMS[(PLATFORMS.index(previous)+1)%len(PLATFORMS)]
