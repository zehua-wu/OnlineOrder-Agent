"""Run the harness against synthetic, contract-shaped backend fixtures.

--model mock: regression only; --model configured: real configured LLM, MOCK
backend, never real cart writes. No metric here establishes production quality.
"""

import argparse
import asyncio
import json
import math
from importlib.resources import files
from pathlib import Path
from statistics import mean
from time import perf_counter

import httpx

from app.agent.orchestrator import AgentOrchestrator
from app.clients.onlineorder_backend import OnlineOrderBackendClient
from app.core.config import Settings
from app.evaluation.mock_backend import USER_ID, DemoBackend
from app.llm.chat_completions import ChatCompletionsModel
from app.llm.mock import MockOrderingModel
from app.memory.coordinator import SessionCoordinator
from app.memory.in_memory import InMemorySessionStore
from app.memory.retrieval import select_memories
from app.models.memory import LongTermMemory
from app.tools.executor import ToolExecutor


def ratio(numerator, denominator):
    return round(numerator / denominator, 6) if denominator else None


def percentile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(values) * p) - 1)], 3)


def wilson(successes, total):
    if not total:
        return None
    z = 1.96
    p = successes / total
    denominator = 1 + z * z / total
    middle = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [round(max(0, middle - half), 6), round(min(1, middle + half), 6)]


async def evaluate_suite(*, model=None, repeats=1):
    cases = json.loads(files("app.evaluation").joinpath("cases.json").read_text())
    latencies, events, observations = [], [], []
    token_input = token_output = model_calls = 0
    for _ in range(repeats):
        for case in cases:
            backend = DemoBackend()
            backend.next_cart_write_error = case.get("fault")
            store = InMemorySessionStore()
            async with httpx.AsyncClient(
                base_url="http://offline.test", transport=httpx.MockTransport(backend.handle)
            ) as http:
                agent = AgentOrchestrator(
                    model=model or MockOrderingModel(),
                    tool_executor=ToolExecutor(OnlineOrderBackendClient(http, read_retries=0)),
                    session_store=store,
                    coordinator=SessionCoordinator(),
                    session_ttl_seconds=3600,
                    recent_message_limit=12,
                    max_tool_steps=5,
                )
                session_id, response = None, None
                case_events = []
                started = perf_counter()
                failure = None
                try:
                    for message in case["messages"]:
                        response = await agent.chat(
                            message=message,
                            session_id=session_id,
                            user_id=USER_ID,
                            authorization="Bearer demo-token",
                        )
                        session_id = response.session_id
                        latencies.append(response.metrics.duration_ms)
                        case_events.extend(response.metrics.tools)
                        token_input += response.metrics.input_tokens
                        token_output += response.metrics.output_tokens
                        model_calls += response.metrics.model_calls
                except Exception as error:  # Report the class only; no provider content/secrets.
                    failure = type(error).__name__
                saved = await store.get(session_id) if session_id else None
                actual_cart = backend.quantities.get(USER_ID, {})
                actual_filters = saved.state.search.model_dump() if saved else {}
                argument_match = all(
                    actual_filters.get(k) == v for k, v in case.get("filters", {}).items()
                )
                relevant = set(case.get("relevant", []))
                returned = (
                    [i.menu_item_id for i in saved.state.last_search_results[:3]] if saved else []
                )
                recall = len(relevant.intersection(returned)) / len(relevant) if relevant else None
                success = failure is None and actual_cart == case["cart"] and argument_match
                success = success and (
                    response is not None and response.error_code == case.get("error")
                )
                if "write_count" in case:
                    success = success and backend.write_count == case["write_count"]
                if "tool_error" in case:
                    success = success and any(e.code == case["tool_error"] for e in case_events)
                if "minimum_results" in case:
                    success = (
                        success
                        and saved is not None
                        and len(saved.state.last_search_results) >= case["minimum_results"]
                    )
                if relevant:
                    success = success and recall == 1
                if case.get("uncertain"):
                    success = success and await agent._journal.barrier(USER_ID) is not None
                if saved and saved.state.pending_action:
                    success = False  # No benchmark task should finish with an unresolved proposal.
                observations.append(
                    {
                        "id": case["id"],
                        "expected_outcome_met": bool(success),
                        "category": case["category"],
                        "task_completed": bool(success) if case["category"] == "business" else None,
                        "failure": failure,
                        "tool_selection_exact": [e.name for e in case_events] == case["tools"],
                        "arguments_match": argument_match if "filters" in case else None,
                        "menu_recall_at_3": recall,
                        "scenario_latency_ms": round((perf_counter() - started) * 1000, 3),
                        "tools": [e.model_dump() for e in case_events],
                        "write_count": backend.write_count,
                    }
                )
                events.extend(case_events)
    # Independent annotated preference-retrieval smoke fixture.
    memories = [
        LongTermMemory(key=f"ingredient.like:{n}", value=f"Likes ingredient {n}") for n in range(20)
    ]
    memories += [
        LongTermMemory(key="allergy.peanut", value="Peanut allergy"),
        LongTermMemory(key="cuisine.thai", value="Likes Thai food"),
    ]
    gold = {"allergy.peanut", "cuisine.thai"}
    retrieved = {m.key for m in select_memories(memories, "Thai food", 8)}
    business = [o for o in observations if o["category"] == "business"]
    safety = [o for o in observations if o["category"] == "safety"]
    completed = sum(o["task_completed"] for o in business)
    passed = sum(o["expected_outcome_met"] for o in observations)
    args = [o["arguments_match"] for o in observations if o["arguments_match"] is not None]
    recalls = [o["menu_recall_at_3"] for o in observations if o["menu_recall_at_3"] is not None]
    writes = [e for e in events if e.name == "commit_add_to_cart"]
    return {
        "suite": "synthetic-contract-v2",
        "model_mode": "configured" if model else "mock",
        "limitations": "Tiny synthetic suite; mock scores validate harness regression only. Latencies exclude HTTP auth and real backend/network. Memory retrieval has one annotated smoke case. No production SLO or model quality claim.",
        "counts": {
            "scenarios": len(observations),
            "scenarios_passed": passed,
            "business_tasks": len(business),
            "safety_cases": len(safety),
            "tasks_completed": completed,
            "tool_attempts": len(events),
            "search_argument_cases": len(args),
            "menu_recall_cases": len(recalls),
            "memory_recall_cases": 1,
            "turns": len(latencies),
            "model_calls": model_calls,
        },
        "metrics": {
            "tool_success_rate": ratio(sum(e.ok for e in events), len(events)),
            "tool_argument_validity_rate": ratio(
                sum(e.code != "INVALID_TOOL_ARGUMENTS" for e in events), len(events)
            ),
            "tool_selection_exact_rate": ratio(
                sum(o["tool_selection_exact"] for o in observations), len(observations)
            ),
            "search_argument_accuracy": ratio(sum(args), len(args)),
            "write_success_rate": ratio(sum(e.ok for e in writes), len(writes)),
            "task_completion_rate": ratio(completed, len(business)),
            "expected_outcome_pass_rate": ratio(passed, len(observations)),
            "safety_case_pass_rate": ratio(
                sum(o["expected_outcome_met"] for o in safety), len(safety)
            ),
            "task_completion_wilson_95_interval": wilson(completed, len(business)),
            "menu_recall_at_3_macro": round(mean(recalls), 6) if recalls else None,
            "memory_recall_at_8": ratio(len(gold & retrieved), len(gold)),
            "turn_latency_p50_ms": percentile(latencies, 0.5),
            "turn_latency_p95_ms": percentile(latencies, 0.95),
            "turn_latency_p99_ms": percentile(latencies, 0.99),
            "input_tokens": token_input,
            "output_tokens": token_output,
        },
        "cases": observations,
    }


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=["mock", "configured"], default="mock")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 100:
        parser.error("--repeats must be between 1 and 100")
    model = ChatCompletionsModel(Settings()) if args.model == "configured" else None
    try:
        report = await evaluate_suite(model=model, repeats=args.repeats)
        report["provider"] = Settings().llm_provider if model else "mock"
        report["model"] = Settings().model_name if model else "deterministic-demo-policy"
    finally:
        if model:
            await model.close()
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if report["metrics"]["expected_outcome_pass_rate"] != 1:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
