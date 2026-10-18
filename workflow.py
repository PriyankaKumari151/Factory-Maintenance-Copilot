"""Explicitly selected workflows, not an autonomous multi-agent system."""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from database import downtime_summary, fault_summary, machines


class State(TypedDict, total=False):        #total=False allows keys to be optional
    question: str
    intent: str
    start_date: str
    end_date: str
    machine_id: str | None
    fault_code: str | None
    evidence: dict
    answer: dict
    trace: list[str]


def build_workflow(retriever, inventory, llm):
    def start(s):
        return {'evidence': {}, 'trace': ['validated_request']}

    def analytics(s):
        rows = downtime_summary(s['start_date'], s['end_date'], s.get('machine_id'))
        evidence = dict(s['evidence'])
        evidence['downtime'] = rows
        if rows:
            machine = rows[0]
            faults = fault_summary(machine['machine_id'], s['start_date'], s['end_date'])
            evidence['selected_machine'] = machine
            evidence['faults'] = faults
        return {'evidence': evidence, 'trace': s['trace'] + ['sql_analytics']}

    def documents(s):
        evidence = dict(s['evidence'])
        selected = evidence.get('selected_machine')
        if not selected and s.get('machine_id'):
            selected = next((m for m in machines() if m['machine_id'] == s['machine_id']), None)
        # Combined mode investigates the fault causing the most RECORDED downtime.
        fault = s.get('fault_code')
        if s['intent'] == 'combined':
            if not evidence.get('faults'):
                evidence['sources'] = []
                evidence['note'] = 'No matching operational events; no troubleshooting inference made.'
                return {'evidence': evidence, 'trace': s['trace'] + ['no_events']}
            fault = evidence['faults'][0]['fault_code']
            evidence['investigated_fault'] = fault
        evidence['sources'] = retriever.retrieve(s['question'], selected['machine_type'] if selected else None, fault)
        return {'evidence': evidence, 'trace': s['trace'] + ['sop_retrieval']}

    def parts(s):
        evidence = dict(s['evidence'])
        ids = sorted({c['part_id'] for c in evidence.get('sources', []) if c.get('part_id')})
        evidence['inventory'] = [inventory.get_part(pid) for pid in ids]
        return {'evidence': evidence, 'trace': s['trace'] + ['inventory_lookup']}

    def answer(s):
        return {'answer': llm.answer(s['question'], s['evidence']), 'trace': s['trace'] + ['answer']}

    graph = StateGraph(State)
    for name, fn in [('start', start), ('analytics', analytics), ('documents', documents), ('parts', parts), ('answer', answer)]:
        graph.add_node(name, fn)
    graph.add_edge(START, 'start')
    graph.add_conditional_edges('start', lambda s: 'documents' if s['intent'] == 'sop' else 'analytics')
    graph.add_conditional_edges('analytics', lambda s: 'documents' if s['intent'] == 'combined' else 'answer')
    graph.add_conditional_edges('documents', lambda s: 'parts' if s['intent'] == 'combined' else 'answer')
    graph.add_edge('parts', 'answer')
    graph.add_edge('answer', END)
    return graph.compile()
