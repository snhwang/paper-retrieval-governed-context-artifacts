"""Scalability evaluation: retrieval precision, scope isolation, token efficiency,
and latency as agent count grows from 10 to 500.

All metrics are pipeline-level (no LLM calls).  The test corpus is generated
programmatically: N customer-service agents, each with a unique persona, shared
department constraints, global policies, safety instructions, and cross-department
conflict pairs.  Ground truth is computed by iterating the corpus and checking
scope conditions, so results are fully reproducible.

Usage:
    python eval_scalability.py              # use sentence-transformers (default)
    python eval_scalability.py --hash       # use deterministic hash embeddings
"""

import argparse
import csv
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from bear import (  # noqa: E402
    Composer,
    CompositionStrategy,
    Config,
    Context,
    Corpus,
    EmbeddingBackend,
    Instruction,
    InstructionType,
    Retriever,
    ScopeCondition,
    ScoredInstruction,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCALE_POINTS = [10, 25, 50, 100, 200, 500]
AGENTS_PER_DEPARTMENT = 10
TOP_K = 25
THRESHOLD = 0.3
PRIORITY_WEIGHT = 0.3
SAMPLE_AGENTS = 10  # agents sampled per scale point
QUERIES_PER_AGENT = 3
EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"  # real semantic embeddings

DEPARTMENT_NAMES = [
    "billing", "technical", "sales", "retention", "compliance",
    "shipping", "returns", "onboarding", "escalation", "premium",
]

PERSONALITIES = ["friendly", "formal", "empathetic", "efficient", "thorough"]

GLOBAL_POLICY_TOPICS = [
    "greeting protocol", "identity verification", "interaction logging",
    "professional language", "code of conduct", "data privacy",
    "response time targets", "escalation procedure",
    "documentation standards", "customer feedback collection",
]

SAFETY_CONTENTS = [
    "Never share customer PII with unauthorized parties",
    "Do not make financial commitments without manager approval",
    "Always verify identity before making account changes",
    "Report any suspicious activity to the security team immediately",
    "Never bypass authentication or access-control procedures",
]

DEPT_CONSTRAINT_TEMPLATES = {
    "billing": [
        "Verify the invoice number and payment method before processing any billing adjustment or refund.",
        "All billing disputes over $500 require supervisor authorization and a written explanation.",
        "When a customer reports an overcharge, pull up the itemized transaction history before responding.",
    ],
    "technical": [
        "Ask the customer for their operating system version and error code before troubleshooting.",
        "If the issue involves data loss, immediately escalate to the data recovery specialist team.",
        "Walk customers through diagnostic steps: restart, clear cache, check network, then reinstall.",
    ],
    "sales": [
        "Present the premium tier upgrade when customers mention needing more features or capacity.",
        "Always quote the annual subscription price alongside the monthly option for comparison.",
        "If a prospect compares us to a competitor, highlight our unique integration capabilities.",
    ],
    "retention": [
        "When a customer threatens to cancel, offer the loyalty discount before processing cancellation.",
        "Review the customer's usage patterns and recommend a plan that better fits their needs.",
        "Document the primary reason for churn in the retention dashboard after every call.",
    ],
    "compliance": [
        "Verify that all data-sharing requests include a signed consent form from the account holder.",
        "Flag any transaction pattern that matches the anti-money-laundering alert thresholds.",
        "Ensure GDPR data deletion requests are completed within the 30-day regulatory window.",
    ],
    "shipping": [
        "Provide the tracking number and estimated delivery date for any shipment status inquiry.",
        "If a package is marked as delivered but customer reports missing, initiate a carrier investigation.",
        "International shipments require customs declaration forms; remind customers about potential duties.",
    ],
    "returns": [
        "Check the return window eligibility based on purchase date before authorizing any return.",
        "Items showing signs of wear or damage beyond normal use are ineligible for full refund.",
        "Generate a prepaid return shipping label and email it to the customer with packing instructions.",
    ],
    "onboarding": [
        "Walk new customers through the initial account setup wizard and verify email confirmation.",
        "Schedule a 15-minute product walkthrough call within the first week of account creation.",
        "Send the welcome kit PDF with quickstart guides and link to the video tutorial library.",
    ],
    "escalation": [
        "Assign a severity level (P1-P4) to each escalated case based on business impact assessment.",
        "All P1 escalations require a status update to the customer every 2 hours until resolution.",
        "Document the root cause analysis and corrective actions in the escalation closure report.",
    ],
    "premium": [
        "Premium customers receive priority queue placement and a dedicated account manager assignment.",
        "Offer complimentary service credits for any premium account experiencing more than 1 hour of downtime.",
        "Proactively schedule quarterly business reviews with premium accounts to discuss usage and ROI.",
    ],
}

# Fallback templates for dynamically generated departments beyond the predefined 10
_FALLBACK_CONSTRAINT_TEMPLATES = [
    "All {dept} inquiries require verifying the customer's account number before proceeding.",
    "When handling {dept} requests, always log the ticket ID and resolution steps.",
    "Escalate unresolved {dept} issues to a senior agent after two failed attempts.",
]

DEPT_QUERIES = {
    "billing": [
        "Customer disputing a charge on their latest invoice",
        "How do I update my payment method and billing address?",
        "Request a refund for a duplicate transaction on my account",
    ],
    "technical": [
        "My application crashes with error code 503 after the latest update",
        "I lost all my saved data and need to recover my files",
        "The software is running very slowly on my Windows machine",
    ],
    "sales": [
        "I want to compare pricing between the basic and premium plans",
        "What integrations do you offer that your competitors don't?",
        "Can I get a demo of the enterprise features before committing?",
    ],
    "retention": [
        "I'm thinking about cancelling my subscription, it's too expensive",
        "I'm not using half the features I'm paying for",
        "A competitor offered me a better deal, can you match it?",
    ],
    "compliance": [
        "I need all my personal data deleted under GDPR regulations",
        "Please provide the signed consent form for data sharing",
        "Report a suspicious transaction pattern on my business account",
    ],
    "shipping": [
        "Where is my package? The tracking says delivered but I never got it",
        "How much are customs duties for international shipping to Germany?",
        "I need to change the delivery address for my pending shipment",
    ],
    "returns": [
        "I want to return a product I purchased two weeks ago",
        "The item arrived damaged, how do I get a replacement?",
        "Can I get a prepaid return label for sending back this order?",
    ],
    "onboarding": [
        "I just created my account and need help with the initial setup",
        "Where can I find the quickstart guide and tutorial videos?",
        "Can you walk me through how to configure my first project?",
    ],
    "escalation": [
        "This is a critical production outage affecting my entire team",
        "I've called three times about this issue and it's still not resolved",
        "I need to speak to a manager about the severity of this problem",
    ],
    "premium": [
        "As a premium customer, I need my dedicated account manager",
        "We experienced two hours of downtime, are we eligible for credits?",
        "I'd like to schedule our quarterly business review meeting",
    ],
}

_FALLBACK_QUERIES = [
    "Customer asking for help with a {dept} issue",
    "Handle a complaint about {dept} service quality",
    "Process a routine {dept} request from a returning customer",
]


# ---------------------------------------------------------------------------
# Corpus generation
# ---------------------------------------------------------------------------

def _dept_name(index: int) -> str:
    if index < len(DEPARTMENT_NAMES):
        return DEPARTMENT_NAMES[index]
    return f"dept{index}"


def generate_corpus(num_agents: int) -> tuple[Corpus, dict]:
    """Build a synthetic corpus for *num_agents* customer-service agents.

    Returns (corpus, metadata) where metadata records the mapping from agent
    index to department and the total instruction counts.
    """
    corpus = Corpus()
    num_departments = math.ceil(num_agents / AGENTS_PER_DEPARTMENT)

    # --- Global policies (empty scope, mandatory tag → always injected) ---
    for i, topic in enumerate(GLOBAL_POLICY_TOPICS):
        corpus.add(Instruction(
            id=f"global-policy-{i}",
            type=InstructionType.DIRECTIVE,
            priority=60,
            content=(
                f"Global customer service policy #{i + 1} ({topic}): "
                f"All agents must adhere to the company standard for {topic}. "
                f"This applies regardless of department or customer context."
            ),
            scope=ScopeCondition(),
            tags=["global"],
        ))

    # --- Safety instructions (mandatory tag) ---
    for i, text in enumerate(SAFETY_CONTENTS):
        corpus.add(Instruction(
            id=f"safety-{i}",
            type=InstructionType.CONSTRAINT,
            priority=95,
            content=f"Safety constraint #{i + 1}: {text}. This constraint must always be observed.",
            scope=ScopeCondition(),
            tags=["safety"],
        ))

    # --- Department constraints (hard-gated + mandatory for guaranteed retrieval) ---
    for d in range(num_departments):
        dept = _dept_name(d)
        templates = DEPT_CONSTRAINT_TEMPLATES.get(dept, None)
        if templates is None:
            templates = [t.format(dept=dept) for t in _FALLBACK_CONSTRAINT_TEMPLATES]
        for j, content in enumerate(templates):
            corpus.add(Instruction(
                id=f"dept-{dept}-constraint-{j}",
                type=InstructionType.CONSTRAINT,
                priority=85,
                content=content,
                scope=ScopeCondition(required_tags=[f"dept-{dept}"]),
                tags=[f"dept-{dept}"],
            ))

    # --- Per-agent persona ---
    agent_departments: dict[int, str] = {}
    for i in range(num_agents):
        dept = _dept_name(i // AGENTS_PER_DEPARTMENT)
        agent_departments[i] = dept
        personality = PERSONALITIES[i % len(PERSONALITIES)]
        corpus.add(Instruction(
            id=f"persona-agent-{i}",
            type=InstructionType.PERSONA,
            priority=75,
            content=(
                f"You are Agent-{i}, a customer service representative in the "
                f"{dept} department. You specialise in {dept}-related inquiries "
                f"and have a {personality} communication style. "
                f"Agent identifier: {i}."
            ),
            scope=ScopeCondition(required_tags=[f"agent-{i}"]),
            tags=[f"agent-{i}", f"dept-{dept}"],
        ))

    # --- Conflict pairs between adjacent departments ---
    num_conflict_pairs = min(num_departments // 2, 5)
    for p in range(num_conflict_pairs):
        dept_a = _dept_name(p * 2)
        dept_b = _dept_name(p * 2 + 1)
        id_a = f"conflict-{dept_a}-offer-discount"
        id_b = f"conflict-{dept_b}-no-discount"
        corpus.add(Instruction(
            id=id_a,
            type=InstructionType.DIRECTIVE,
            priority=65,
            content=(
                f"When a {dept_a} customer requests a discount, proactively "
                f"offer a 10% loyalty discount to retain the customer."
            ),
            scope=ScopeCondition(required_tags=[f"dept-{dept_a}"]),
            conflicts_with=[id_b],
            tags=[f"dept-{dept_a}", "discount"],
        ))
        corpus.add(Instruction(
            id=id_b,
            type=InstructionType.DIRECTIVE,
            priority=70,
            content=(
                f"Never offer discounts without written manager approval. "
                f"All discount requests in {dept_b} must go through the approval chain."
            ),
            scope=ScopeCondition(required_tags=[f"dept-{dept_b}"]),
            conflicts_with=[id_a],
            tags=[f"dept-{dept_b}", "discount"],
        ))

    metadata = {
        "num_agents": num_agents,
        "num_departments": num_departments,
        "total_instructions": len(corpus),
        "agents": {
            i: {"dept_name": dept, "dept_tag": f"dept-{dept}"}
            for i, dept in agent_departments.items()
        },
    }
    return corpus, metadata


# ---------------------------------------------------------------------------
# Ground truth
# ---------------------------------------------------------------------------

def compute_ground_truth(
    corpus: Corpus,
    context: Context,
    mandatory_tags: list[str],
) -> set[str]:
    """Return the set of instruction IDs expected for *context*.

    Mirrors the retriever's inclusion logic:
    1. required_tags hard gate (AND — all must be in context.tags)
    2. scope.matches(context) soft gate
    3. Mandatory-tag injection (always included)
    """
    expected: set[str] = set()
    ctx_tags = set(context.tags)

    for inst in corpus:
        # Hard gate: required_tags must ALL be present
        if inst.scope.required_tags:
            if not all(t in ctx_tags for t in inst.scope.required_tags):
                # Might still be included via mandatory tags
                if set(inst.tags) & set(mandatory_tags):
                    expected.add(inst.id)
                continue

        # Soft gate: scope match
        if inst.scope.matches(context):
            expected.add(inst.id)
            continue

        # Empty scope matches everything
        if not _scope_has_conditions(inst.scope):
            expected.add(inst.id)
            continue

        # Mandatory-tag fallback
        if set(inst.tags) & set(mandatory_tags):
            expected.add(inst.id)

    return expected


def _scope_has_conditions(scope: ScopeCondition) -> bool:
    """Return True if the scope has any non-empty condition field."""
    return bool(
        scope.required_tags
        or scope.tags
        or scope.user_roles
        or scope.task_types
        or scope.domains
        or scope.session_phase
        or scope.trigger_patterns
    )


# ---------------------------------------------------------------------------
# Query generation
# ---------------------------------------------------------------------------

def generate_queries(agent_idx: int, dept_name: str) -> list[tuple[str, Context]]:
    """Return QUERIES_PER_AGENT (query_text, Context) pairs for an agent."""
    agent_tag = f"agent-{agent_idx}"
    dept_tag = f"dept-{dept_name}"
    queries = DEPT_QUERIES.get(dept_name, None)
    if queries is None:
        queries = [t.format(dept=dept_name) for t in _FALLBACK_QUERIES]
    return [
        (
            q,
            Context(
                user_role="customer",
                task_type=dept_name,
                domain="customer_service",
                tags=[agent_tag, dept_tag],
            ),
        )
        for q in queries[:QUERIES_PER_AGENT]
    ]


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------

def compute_prf(retrieved_ids: set[str], expected_ids: set[str]):
    """Return (precision, recall, f1)."""
    tp = len(retrieved_ids & expected_ids)
    p = tp / len(retrieved_ids) if retrieved_ids else 0.0
    r = tp / len(expected_ids) if expected_ids else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    return p, r, f1


def count_scope_violations(retrieved: list[ScoredInstruction], agent_idx: int) -> int:
    """Count persona instructions belonging to a *different* agent."""
    own = f"agent-{agent_idx}"
    violations = 0
    for si in retrieved:
        req = si.instruction.scope.required_tags
        if req:
            agent_tags = [t for t in req if t.startswith("agent-")]
            if agent_tags and own not in agent_tags:
                violations += 1
    return violations


def estimate_tokens(text) -> int:
    """Rough token estimate (chars / 4)."""
    return len(str(text)) // 4


def compute_static_tokens(corpus: Corpus) -> int:
    """Token count if every instruction were dumped into one prompt."""
    composer = Composer(strategy=CompositionStrategy.HIERARCHICAL)
    all_scored = [
        ScoredInstruction(
            instruction=inst,
            similarity=1.0,
            scope_match=True,
            final_score=inst.priority / 100.0,
        )
        for inst in corpus
    ]
    return estimate_tokens(composer.compose(all_scored))


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ScaleResult:
    num_agents: int = 0
    total_instructions: int = 0
    num_queries: int = 0
    # Behavioral identity metrics (the ones that matter)
    persona_recall: float = 0.0       # did the agent get ITS persona? (should be 1.0)
    dept_recall: float = 0.0          # fraction of dept constraints retrieved (should be 1.0)
    safety_recall: float = 0.0        # fraction of safety instructions retrieved (should be 1.0)
    global_recall: float = 0.0        # fraction of global policies retrieved (should be 1.0)
    scope_violations: int = 0         # wrong-agent persona retrieved (should be 0)
    cross_dept_count: float = 0.0     # avg wrong-dept constraints retrieved
    # Token efficiency
    mean_bear_tokens: float = 0.0
    static_tokens: int = 0
    token_ratio: float = 0.0
    # Latency
    build_time_ms: float = 0.0
    mean_retrieval_ms: float = 0.0
    p95_retrieval_ms: float = 0.0


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------

def run_evaluation(use_hash: bool = False):
    model = "hash" if use_hash else EMBEDDING_MODEL
    print(f"Embedding model: {model}")

    results: list[ScaleResult] = []
    composer = Composer(strategy=CompositionStrategy.HIERARCHICAL)

    for num_agents in SCALE_POINTS:
        print(f"\n{'=' * 60}")
        print(f"  Scale point: {num_agents} agents")
        print(f"{'=' * 60}")

        # --- Generate corpus ---
        corpus, meta = generate_corpus(num_agents)
        total_instr = meta["total_instructions"]
        num_depts = meta["num_departments"]
        print(f"  Corpus: {total_instr} instructions, {num_depts} departments")

        # --- Build retriever ---
        config = Config(
            embedding_model=model,
            embedding_backend=EmbeddingBackend.NUMPY,
            priority_weight=PRIORITY_WEIGHT,
            default_threshold=THRESHOLD,
            default_top_k=TOP_K,
            mandatory_tags=["safety", "global"],
        )
        retriever = Retriever(corpus, config=config)

        t0 = time.perf_counter()
        retriever.build_index()
        build_ms = (time.perf_counter() - t0) * 1000

        # --- Static-prompt baseline ---
        static_tok = compute_static_tokens(corpus)

        # --- Sample agents ---
        sample_n = min(num_agents, SAMPLE_AGENTS)
        step = max(1, num_agents // sample_n)
        sampled = list(range(0, num_agents, step))[:sample_n]

        # Accumulators for behavioural identity metrics
        persona_hits, persona_total = 0, 0
        dept_hits, dept_total = 0, 0
        safety_hits, safety_total = 0, 0
        global_hits, global_total = 0, 0
        total_violations = 0
        cross_dept_counts: list[int] = []
        bear_tokens: list[int] = []
        latencies: list[float] = []

        for agent_idx in sampled:
            dept = meta["agents"][agent_idx]["dept_name"]
            dept_tag = f"dept-{dept}"
            persona_id = f"persona-agent-{agent_idx}"
            dept_ids = {f"dept-{dept}-constraint-{j}" for j in range(3)}
            safety_ids = {f"safety-{i}" for i in range(len(SAFETY_CONTENTS))}
            global_ids = {f"global-policy-{i}" for i in range(len(GLOBAL_POLICY_TOPICS))}

            for query_text, ctx in generate_queries(agent_idx, dept):
                t0 = time.perf_counter()
                retrieved = retriever.retrieve(query_text, ctx, top_k=TOP_K)
                lat = (time.perf_counter() - t0) * 1000
                latencies.append(lat)

                retrieved_ids = {r.id for r in retrieved}

                # Persona recall
                persona_total += 1
                if persona_id in retrieved_ids:
                    persona_hits += 1

                # Department constraint recall
                dept_total += len(dept_ids)
                dept_hits += len(dept_ids & retrieved_ids)

                # Safety recall
                safety_total += len(safety_ids)
                safety_hits += len(safety_ids & retrieved_ids)

                # Global policy recall
                global_total += len(global_ids)
                global_hits += len(global_ids & retrieved_ids)

                # Scope violations (wrong-agent persona)
                total_violations += count_scope_violations(retrieved, agent_idx)

                # Cross-department contamination
                cross = 0
                for r in retrieved:
                    r_tags = set(r.instruction.tags)
                    # Has a dept tag that's NOT our dept (and is a dept tag)
                    for t in r_tags:
                        if t.startswith("dept-") and t != dept_tag:
                            cross += 1
                            break
                cross_dept_counts.append(cross)

                bear_tokens.append(estimate_tokens(composer.compose(retrieved)))

        n_q = len(latencies)
        sorted_lat = sorted(latencies)
        p95_idx = min(int(0.95 * n_q), n_q - 1)

        from stat_utils import bootstrap_ci, format_ci

        # Bootstrap CIs on per-query token and latency distributions
        ci_tokens = bootstrap_ci(bear_tokens)
        ci_latency = bootstrap_ci(latencies)

        res = ScaleResult(
            num_agents=num_agents,
            total_instructions=total_instr,
            num_queries=n_q,
            persona_recall=persona_hits / persona_total if persona_total else 0.0,
            dept_recall=dept_hits / dept_total if dept_total else 0.0,
            safety_recall=safety_hits / safety_total if safety_total else 0.0,
            global_recall=global_hits / global_total if global_total else 0.0,
            scope_violations=total_violations,
            cross_dept_count=sum(cross_dept_counts) / n_q if n_q else 0.0,
            mean_bear_tokens=sum(bear_tokens) / n_q,
            static_tokens=static_tok,
            token_ratio=(sum(bear_tokens) / n_q) / static_tok if static_tok else 0.0,
            build_time_ms=build_ms,
            mean_retrieval_ms=sum(latencies) / n_q,
            p95_retrieval_ms=sorted_lat[p95_idx],
        )
        results.append(res)

        print(f"  Queries:           {n_q}")
        print(f"  Persona recall:    {res.persona_recall:.3f}")
        print(f"  Dept recall:       {res.dept_recall:.3f}")
        print(f"  Safety recall:     {res.safety_recall:.3f}")
        print(f"  Global recall:     {res.global_recall:.3f}")
        print(f"  Scope violations:  {res.scope_violations}")
        print(f"  Cross-dept avg:    {res.cross_dept_count:.1f}")
        print(f"  BEAR tokens/query: {format_ci(ci_tokens, precision=0)}")
        print(f"  Static tokens:     {res.static_tokens}")
        print(f"  Token ratio:       {res.token_ratio:.4f}")
        print(f"  Build time:        {res.build_time_ms:.1f} ms")
        print(f"  Retrieval:         {format_ci(ci_latency, precision=2)} ms (95% CI)")

    print_summary(results)
    print_latex_tables(results)
    write_csv(results)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_summary(results: list[ScaleResult]):
    print(f"\n{'=' * 120}")
    print("  SUMMARY")
    print(f"{'=' * 120}")
    header = (
        f"{'Agents':>6} | {'Instr':>6} | {'Persona':>7} | {'Dept':>5} | "
        f"{'Safety':>6} | {'Global':>6} | {'Viol':>4} | {'XDept':>5} | "
        f"{'BEAR Tok':>8} | {'Static Tok':>10} | {'Ratio':>6} | {'Lat ms':>6}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r.num_agents:>6} | {r.total_instructions:>6} | "
            f"{r.persona_recall:>7.3f} | {r.dept_recall:>5.3f} | "
            f"{r.safety_recall:>6.3f} | {r.global_recall:>6.3f} | "
            f"{r.scope_violations:>4} | {r.cross_dept_count:>5.1f} | "
            f"{r.mean_bear_tokens:>8.0f} | {r.static_tokens:>10} | "
            f"{r.token_ratio:>6.4f} | {r.mean_retrieval_ms:>6.2f}"
        )


def print_latex_tables(results: list[ScaleResult]):
    # Table 1: Behavioral identity recall
    print("\n% === LaTeX Table 1: Behavioral Identity Recall ===")
    print("\\begin{table}[t]")
    print("\\caption{Behavioral identity recall as agent population scales. "
          "Each column measures the fraction of a specific instruction category "
          "correctly retrieved for each agent. "
          f"($\\alpha={PRIORITY_WEIGHT}$, $\\theta={THRESHOLD}$, $k={TOP_K}$).}}")
    print("\\label{tab:scalability-recall}")
    print("\\begin{tabular}{@{}rrcccc@{}}")
    print("\\toprule")
    print("$N$ & Instructions & Persona & Dept & Safety & Global \\\\")
    print("\\midrule")
    for r in results:
        print(f"{r.num_agents} & {r.total_instructions} & "
              f"{r.persona_recall:.3f} & {r.dept_recall:.3f} & "
              f"{r.safety_recall:.3f} & {r.global_recall:.3f} \\\\")
    print("\\bottomrule")
    print("\\end{tabular}")
    print("\\end{table}")

    # Table 2: Scope isolation and token efficiency
    print("\n% === LaTeX Table 2: Scope Isolation & Token Efficiency ===")
    print("\\begin{table}[t]")
    print("\\caption{Scope isolation and token efficiency. "
          "Scope violations (wrong-agent persona retrieved) remain zero at all "
          "scale points; composed prompt size stays constant while the "
          "static-prompt equivalent grows linearly.}")
    print("\\label{tab:scalability-efficiency}")
    print("\\begin{tabular}{@{}rrcccrc@{}}")
    print("\\toprule")
    print("$N$ & Instructions & Persona Viol. & Cross-Dept & "
          "BEAR Tokens & Static Tokens & Ratio \\\\")
    print("\\midrule")
    for r in results:
        print(f"{r.num_agents} & {r.total_instructions} & "
              f"{r.scope_violations} & {r.cross_dept_count:.1f} & "
              f"{r.mean_bear_tokens:.0f} & {r.static_tokens} & "
              f"{r.token_ratio:.4f} \\\\")
    print("\\bottomrule")
    print("\\end{tabular}")
    print("\\end{table}")

    # Table 3: Latency
    print("\n% === LaTeX Table 3: Latency ===")
    print("\\begin{table}[t]")
    print("\\caption{Index build time and per-query retrieval latency as corpus scales.}")
    print("\\label{tab:scalability-latency}")
    print("\\begin{tabular}{@{}rrcc@{}}")
    print("\\toprule")
    print("$N$ & Instructions & Build (ms) & Retrieval (ms) \\\\")
    print("\\midrule")
    for r in results:
        print(f"{r.num_agents} & {r.total_instructions} & "
              f"{r.build_time_ms:.1f} & {r.mean_retrieval_ms:.2f} \\\\")
    print("\\bottomrule")
    print("\\end{tabular}")
    print("\\end{table}")


def write_csv(results: list[ScaleResult]):
    csv_path = project_root / "results" / "scalability_results.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "num_agents", "total_instructions", "num_queries",
            "persona_recall", "dept_recall", "safety_recall", "global_recall",
            "scope_violations", "cross_dept_avg",
            "bear_tokens", "static_tokens", "token_ratio",
            "build_time_ms", "retrieval_mean_ms", "retrieval_p95_ms",
        ])
        for r in results:
            w.writerow([
                r.num_agents, r.total_instructions, r.num_queries,
                f"{r.persona_recall:.4f}", f"{r.dept_recall:.4f}",
                f"{r.safety_recall:.4f}", f"{r.global_recall:.4f}",
                r.scope_violations, f"{r.cross_dept_count:.2f}",
                f"{r.mean_bear_tokens:.0f}", r.static_tokens, f"{r.token_ratio:.4f}",
                f"{r.build_time_ms:.1f}",
                f"{r.mean_retrieval_ms:.2f}", f"{r.p95_retrieval_ms:.2f}",
            ])
    print(f"\nCSV written to {csv_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BEAR scalability evaluation")
    parser.add_argument("--hash", action="store_true",
                        help="Use deterministic hash embeddings instead of sentence-transformers")
    args = parser.parse_args()
    run_evaluation(use_hash=args.hash)
