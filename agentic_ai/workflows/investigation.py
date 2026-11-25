"""Bounded deterministic LangGraph investigation of fictional denied claim lines."""
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from generative_ai.retrieval.policies import explain


class State(TypedDict, total=False):
    line: dict
    explanation: dict
    evidence: dict
    citation: dict | None
    findings: list[str]
    appeal_draft: str | None
    trace: Annotated[list[str], operator.add]


def intake(state: State):
    line = state["line"]
    evidence = {name: line[name] for name in ("eligibility", "authorizations", "duplicates")}
    return {"evidence": evidence, "trace": ["Claims intake"]}


def verify(state: State):
    line, evidence = state["line"], state["evidence"]
    candidate = state["explanation"]["policy"]
    citation = candidate if candidate and (
        candidate["payer"] == line["payer"] and candidate["procedure"] == line["procedure"]
        and candidate["starts"] <= line["service"] < candidate["ends"]
    ) else None
    findings = []
    if not citation:
        findings.append("No verified policy section covers this payer, procedure and service date.")
    if line["reason"] == "AUTH" and not evidence["authorizations"]:
        findings.append("No matching authorization appears in the extract. Verify the source record.")
    if line["reason"] == "ELIG" and not evidence["eligibility"]:
        findings.append("No matching eligibility appears in the extract. Verify coverage with the payer.")
    if line["reason"] == "DUP":
        findings.append("Compare the original submission with the payer's duplicate reference before drafting.")
    if not findings:
        findings.append("Compare the exact cited policy and available extract records with the payer's documentation.")
    return {"citation": citation, "findings": findings, "trace": ["Policy and evidence verification"]}


def route(state: State):
    reason = state["line"]["reason"]
    key = {"AUTH": "authorizations", "ELIG": "eligibility"}.get(reason)
    return "draft" if state["citation"] and key and state["evidence"][key] else "handoff"


def draft(state: State):
    line, citation = state["line"], state["citation"]
    key = {"AUTH": "authorizations", "ELIG": "eligibility"}[line["reason"]]
    ids = ", ".join(record["id"] for record in state["evidence"][key])
    body = (
        f"Draft reconsideration request for {line['id']} to {line['payer']}. "
        f"The recorded reason is “{state['explanation']['reason']}” ({line['reason']}). "
        f"For service on {line['service']}, the billing extract contains {key} record(s) {ids}. "
        f"Please reconcile these records with {citation['id']}, {citation['section']}: "
        f"“{citation['excerpt']}” Verify source records before submitting any request."
    )
    return {"appeal_draft": body, "trace": ["Appeal draft"]}


def handoff(state: State):
    return {"trace": ["Awaiting human review"]}


def build_graph():
    graph = StateGraph(State)
    retry = RetryPolicy(max_attempts=2, initial_interval=0.1, retry_on=(TimeoutError,))
    graph.add_node("intake", intake, retry_policy=retry)
    graph.add_node("verify", verify, retry_policy=retry)
    graph.add_node("draft", draft)
    graph.add_node("handoff", handoff)
    graph.add_edge(START, "intake")
    graph.add_edge("intake", "verify")
    graph.add_conditional_edges("verify", route, {"draft": "draft", "handoff": "handoff"})
    graph.add_edge("draft", "handoff")
    graph.add_edge("handoff", END)
    return graph.compile()


GRAPH = build_graph()


def investigate(db, line):
    explanation = explain(db, line)
    if explanation is None:
        raise ValueError("Investigations require a recorded denial.")
    result = GRAPH.invoke({"line": line, "explanation": explanation}, {"recursion_limit": 8})
    return {
        "line_id": line["id"], "recorded_reason": explanation["reason"], "reason_code": explanation["code"],
        "service_date": line["service"], "policy": result["citation"],
        "findings": result["findings"], "evidence": result["evidence"],
        "suggested_action": explanation["action"] if result["citation"] else "Request payer clarification",
        "appeal_draft": result.get("appeal_draft"), "trace": result["trace"],
    }
