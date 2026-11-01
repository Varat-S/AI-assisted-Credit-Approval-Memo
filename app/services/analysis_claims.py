"""Read-only claim-origin projection; never infers origin from IDs or wording.

Coverage adjustments describe the last synthesizer answer, not every historical
conclusion. Only a matching recorded producer can positively identify a copy.
Unmarked/ambiguous historical claims stay in the validated final conclusion;
absence of an insertion record is not proof of model authorship.
"""
from app.services.bo.plans import BO_ORCHESTRATOR_ID

COVERAGE_INSERTION_NOTE = 'Included a validated specialist finding omitted from the model synthesis.'
ORIGIN_NOTICE = ('Individual claim origin is not separately classified for retained claims. '
                 'They are taken from this run’s validated, post-challenge conclusion. '
                 'Documented automatic coverage copies are omitted.')


def automatic_coverage_ids(audit, conclusion):
    """Exact IDs positively marked for this frozen conclusion's producer."""
    orchestrator = audit.get('orchestrator')
    if not isinstance(orchestrator, dict):
        return set()
    history = orchestrator.get('history')
    producer = conclusion.get('orchestrator_run_id')
    if not producer or not isinstance(history, list) or not history:
        return set()
    last = history[-1]
    if (not isinstance(last, dict) or last.get('agent_run_id') != producer
            or last.get('status') not in {'accepted', 'accepted_unvalidated'}):
        return set()
    if (conclusion.get('payload') or {}).get('orchestrator_run_id') not in (None, producer):
        return set()
    agents = [agent for agent in audit.get('agents') or []
              if agent.get('agent_id') == BO_ORCHESTRATOR_ID]
    if len(agents) != 1 or agents[0].get('status') != 'validated':
        return set()
    agent = agents[0]
    runs = agent.get('runs') or []
    if not isinstance(runs, list) or (runs and (not isinstance(runs[-1], dict)
                                              or runs[-1].get('agent_run_id') != producer)):
        return set()
    return {item['claim_id'] for item in agent.get('validator_adjustments') or []
            if isinstance(item, dict) and item.get('note') == COVERAGE_INSERTION_NOTE
            and isinstance(item.get('claim_id'), str) and item['claim_id']}
