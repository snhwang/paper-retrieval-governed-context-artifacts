"""Baseline comparison: BEAR vs. Conditional Prompt Assembly (CPA).

Compares BEAR's semantic retrieval pipeline against the standard practice
of layered prompt construction with lookup tables and conditional logic.
Both systems receive identical instruction content; the difference is
HOW each selects instructions for a given agent and query context.

Uses the same synthetic corpus, queries, and ground truth as
eval_scalability.py for direct comparability.

Usage:
    python eval_baseline_comparison.py              # sentence-transformers
    python eval_baseline_comparison.py --hash       # deterministic hash embeddings
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
# Allow importing sibling eval scripts
sys.path.insert(0, str(Path(__file__).resolve().parent))

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

from eval_scalability import (  # noqa: E402
    generate_corpus,
    generate_queries,
    compute_ground_truth,
    count_scope_violations,
    estimate_tokens,
    compute_static_tokens,
    compute_prf,
    _dept_name,
    SCALE_POINTS,
    SAMPLE_AGENTS,
    QUERIES_PER_AGENT,
    TOP_K,
    THRESHOLD,
    PRIORITY_WEIGHT,
    EMBEDDING_MODEL,
    DEPARTMENT_NAMES,
    SAFETY_CONTENTS,
    GLOBAL_POLICY_TOPICS,
    AGENTS_PER_DEPARTMENT,
)

# ---------------------------------------------------------------------------
# Conditional Prompt Assembly baseline
# ---------------------------------------------------------------------------

class ConditionalPromptAssembler:
    """Baseline: layered prompt construction with lookup tables.

    Models the standard production practice of building system prompts
    via a base block + conditional blocks selected by if/elif logic.
    """

    def __init__(self, corpus: Corpus, metadata: dict) -> None:
        self.safety_instructions: list[Instruction] = []
        self.global_instructions: list[Instruction] = []
        self.persona_by_agent: dict[int, Instruction] = {}
        self.constraints_by_dept: dict[str, list[Instruction]] = {}
        self.discount_by_dept: dict[str, Instruction] = {}

        for inst in corpus:
            if "safety" in inst.tags:
                self.safety_instructions.append(inst)
            elif "global" in inst.tags:
                self.global_instructions.append(inst)
            elif inst.id.startswith("persona-agent-"):
                idx = int(inst.id.split("-")[-1])
                self.persona_by_agent[idx] = inst
            elif inst.id.startswith("dept-") and "-constraint-" in inst.id:
                # e.g. "dept-billing-constraint-0"
                parts = inst.id.split("-constraint-")
                dept = parts[0].replace("dept-", "", 1)
                self.constraints_by_dept.setdefault(dept, []).append(inst)
            elif inst.id.startswith("conflict-") and "-offer-discount" in inst.id:
                dept = inst.id.replace("conflict-", "").replace("-offer-discount", "")
                self.discount_by_dept[dept] = inst
            elif inst.id.startswith("conflict-") and "-no-discount" in inst.id:
                dept = inst.id.replace("conflict-", "").replace("-no-discount", "")
                # Only store if no offer-discount entry already (prefer the one matching dept)
                if dept not in self.discount_by_dept:
                    self.discount_by_dept[dept] = inst

        num_departments = metadata["num_departments"]
        num_agents = metadata["num_agents"]
        discount_count = len(self.discount_by_dept)

        # Estimated lines of wiring code a developer must write/maintain:
        # base structure (3) + dept lookup entries + agent persona entries + discount branches
        self.wiring_lines = 3 + num_departments + num_agents + discount_count
        self.num_lookup_tables = 5  # safety, global, persona, constraints, discount

    def retrieve(
        self,
        agent_idx: int,
        dept_name: str,
        context_tags: list[str],
    ) -> list[ScoredInstruction]:
        """Deterministic instruction selection via lookup tables."""
        selected: list[ScoredInstruction] = []

        def _wrap(inst: Instruction) -> ScoredInstruction:
            return ScoredInstruction(
                instruction=inst,
                similarity=1.0,
                scope_match=True,
                final_score=inst.priority / 100.0,
            )

        # Always include safety
        for inst in self.safety_instructions:
            selected.append(_wrap(inst))

        # Always include global policies
        for inst in self.global_instructions:
            selected.append(_wrap(inst))

        # Department constraints (lookup)
        if dept_name in self.constraints_by_dept:
            for inst in self.constraints_by_dept[dept_name]:
                selected.append(_wrap(inst))

        # Agent persona (lookup)
        if agent_idx in self.persona_by_agent:
            selected.append(_wrap(self.persona_by_agent[agent_idx]))

        # Conditional: discount tag present
        if "discount" in context_tags and dept_name in self.discount_by_dept:
            selected.append(_wrap(self.discount_by_dept[dept_name]))

        return selected


# ---------------------------------------------------------------------------
# Semantic-only instructions (Phase 3: Semantic Retrieval Advantage)
# ---------------------------------------------------------------------------
# Instructions with NO required_tags, NO mandatory tags, and scopes with
# task_types that don't match standard query contexts.  Discoverable ONLY
# through vector similarity search (similarity >= threshold).

SEMANTIC_INSTRUCTIONS = [
    # --- Category A: Semantically scoped (content similarity only) ---
    {
        "id": "semantic-emotional-handling",
        "type": InstructionType.DIRECTIVE,
        "priority": 70,
        "content": (
            "When a customer expresses frustration, anger, or distress, "
            "acknowledge their emotions before addressing the technical issue. "
            "Use phrases like 'I understand this is frustrating' and 'Let me help "
            "resolve this for you.' Never dismiss or minimize the customer's feelings."
        ),
        "scope": ScopeCondition(task_types=["emotional_support"]),
        "tags": ["communication"],
    },
    {
        "id": "semantic-data-migration",
        "type": InstructionType.PROTOCOL,
        "priority": 75,
        "content": (
            "For any request involving moving data between accounts, transferring "
            "subscription ownership, or migrating service configurations, require "
            "written authorization from both the source and destination account holders "
            "before proceeding with the transfer."
        ),
        "scope": ScopeCondition(task_types=["account_transfer"]),
        "tags": ["data-handling"],
    },
    {
        "id": "semantic-regulatory-disclosure",
        "type": InstructionType.CONSTRAINT,
        "priority": 90,
        "content": (
            "When discussing pricing, fees, or charges, always disclose any "
            "applicable regulatory fees, taxes, and surcharges upfront. Do not "
            "present base prices without mentioning additional mandatory costs. "
            "This applies to all customer-facing price communications."
        ),
        "scope": ScopeCondition(task_types=["pricing_transparency"]),
        "tags": ["regulatory"],
    },

    # --- Category B: Paraphrased / indirect queries ---
    {
        "id": "semantic-identity-verification",
        "type": InstructionType.CONSTRAINT,
        "priority": 85,
        "content": (
            "Before making any modifications to account settings, contact "
            "information, payment methods, or security credentials, confirm the "
            "requester's identity through security questions or two-factor "
            "authentication. Log all verification attempts."
        ),
        "scope": ScopeCondition(task_types=["account_security"]),
        "tags": ["verification"],
    },
    {
        "id": "semantic-service-downgrade",
        "type": InstructionType.DIRECTIVE,
        "priority": 65,
        "content": (
            "When processing a subscription tier reduction or feature removal, "
            "clearly explain what capabilities will be lost, any data that may "
            "become inaccessible, and the effective date of changes. Offer a "
            "trial extension of the current tier if the customer is uncertain."
        ),
        "scope": ScopeCondition(task_types=["plan_management"]),
        "tags": ["subscription"],
    },
    {
        "id": "semantic-outage-communication",
        "type": InstructionType.PROTOCOL,
        "priority": 80,
        "content": (
            "During a service disruption or system outage, provide the customer "
            "with the incident ticket number, estimated time to resolution, and "
            "a link to the status page. Do not speculate about the root cause "
            "or make promises about exact restoration times."
        ),
        "scope": ScopeCondition(task_types=["incident_response"]),
        "tags": ["outage"],
    },

    # --- Category C: Cross-cutting concerns ---
    {
        "id": "semantic-de-escalation",
        "type": InstructionType.DIRECTIVE,
        "priority": 72,
        "content": (
            "When a conversation becomes heated or the customer threatens to "
            "leave, cancel, or take legal action, apply de-escalation techniques: "
            "lower your tone, summarize their concern to show understanding, offer "
            "concrete next steps, and provide a direct callback number for follow-up."
        ),
        "scope": ScopeCondition(task_types=["conflict_resolution"]),
        "tags": ["de-escalation"],
    },
    {
        "id": "semantic-accessibility",
        "type": InstructionType.DIRECTIVE,
        "priority": 68,
        "content": (
            "Accommodate customers with accessibility needs by offering "
            "alternative communication channels, providing information in "
            "plain language, allowing extra time for responses, and ensuring "
            "all shared links and documents meet accessibility standards."
        ),
        "scope": ScopeCondition(task_types=["accessibility"]),
        "tags": ["accessibility"],
    },
    {
        "id": "semantic-multilingual-support",
        "type": InstructionType.DIRECTIVE,
        "priority": 66,
        "content": (
            "If a customer communicates in a language other than English or "
            "indicates limited English proficiency, offer to connect them with "
            "a bilingual agent or activate the translation assistance service. "
            "Never assume language preference based on account region."
        ),
        "scope": ScopeCondition(task_types=["language_services"]),
        "tags": ["multilingual"],
    },

    # --- Category D: Compositional novelty ---
    {
        "id": "semantic-premium-escalation",
        "type": InstructionType.PROTOCOL,
        "priority": 78,
        "content": (
            "High-value accounts experiencing service issues require expedited "
            "handling: assign a senior specialist within 15 minutes, waive "
            "diagnostic fees, and proactively offer service credits without "
            "waiting for the customer to request compensation."
        ),
        "scope": ScopeCondition(task_types=["vip_handling"]),
        "tags": ["premium-service"],
    },
    {
        "id": "semantic-compliance-billing",
        "type": InstructionType.CONSTRAINT,
        "priority": 88,
        "content": (
            "When a billing dispute involves regulatory compliance implications "
            "such as unauthorized charges, consumer protection claims, or "
            "contractual violations, immediately involve the legal review team "
            "before offering any settlement or adjustment."
        ),
        "scope": ScopeCondition(task_types=["legal_review"]),
        "tags": ["compliance-billing"],
    },
    {
        "id": "semantic-technical-billing",
        "type": InstructionType.DIRECTIVE,
        "priority": 70,
        "content": (
            "When a customer reports being charged for a service that was not "
            "functioning due to a technical fault on our end, automatically "
            "qualify them for a prorated refund covering the documented outage "
            "period without requiring manager approval."
        ),
        "scope": ScopeCondition(task_types=["fault_compensation"]),
        "tags": ["tech-billing"],
    },
]

SEMANTIC_QUERIES = [
    # --- Category A: Semantically scoped ---
    {
        "text": "The customer is extremely upset about repeated billing errors and is yelling",
        "context": Context(
            user_role="customer",
            task_type="billing",
            domain="customer_service",
            tags=["agent-0", "dept-billing"],
        ),
        "expected_semantic_ids": {"semantic-emotional-handling"},
        "scenario_type": "semantically_scoped",
    },
    {
        "text": "Customer wants to transfer their account and all associated data to their business partner",
        "context": Context(
            user_role="customer",
            task_type="sales",
            domain="customer_service",
            tags=["agent-0", "dept-sales"],
        ),
        "expected_semantic_ids": {"semantic-data-migration"},
        "scenario_type": "semantically_scoped",
    },
    {
        "text": "What is the total cost including all fees and taxes for the premium plan?",
        "context": Context(
            user_role="customer",
            task_type="sales",
            domain="customer_service",
            tags=["agent-0", "dept-sales"],
        ),
        "expected_semantic_ids": {"semantic-regulatory-disclosure"},
        "scenario_type": "semantically_scoped",
    },

    # --- Category B: Paraphrased / indirect queries ---
    {
        "text": "Someone wants to update their email address and phone number on file",
        "context": Context(
            user_role="customer",
            task_type="technical",
            domain="customer_service",
            tags=["agent-0", "dept-technical"],
        ),
        "expected_semantic_ids": {"semantic-identity-verification"},
        "scenario_type": "paraphrased_query",
    },
    {
        "text": "I want to switch to a cheaper plan with fewer features",
        "context": Context(
            user_role="customer",
            task_type="retention",
            domain="customer_service",
            tags=["agent-0", "dept-retention"],
        ),
        "expected_semantic_ids": {"semantic-service-downgrade"},
        "scenario_type": "paraphrased_query",
    },
    {
        "text": "Everything is down and nothing is working, when will it be fixed?",
        "context": Context(
            user_role="customer",
            task_type="technical",
            domain="customer_service",
            tags=["agent-0", "dept-technical"],
        ),
        "expected_semantic_ids": {"semantic-outage-communication"},
        "scenario_type": "paraphrased_query",
    },

    # --- Category C: Cross-cutting concerns ---
    {
        "text": "Customer is threatening to cancel and go to a competitor over a billing mistake",
        "context": Context(
            user_role="customer",
            task_type="billing",
            domain="customer_service",
            tags=["agent-0", "dept-billing"],
        ),
        "expected_semantic_ids": {"semantic-de-escalation"},
        "scenario_type": "cross_cutting",
    },
    {
        "text": "The customer has a visual impairment and needs help navigating the website",
        "context": Context(
            user_role="customer",
            task_type="technical",
            domain="customer_service",
            tags=["agent-0", "dept-technical"],
        ),
        "expected_semantic_ids": {"semantic-accessibility"},
        "scenario_type": "cross_cutting",
    },
    {
        "text": "Customer is writing in Spanish and seems to have trouble understanding English instructions",
        "context": Context(
            user_role="customer",
            task_type="onboarding",
            domain="customer_service",
            tags=["agent-0", "dept-onboarding"],
        ),
        "expected_semantic_ids": {"semantic-multilingual-support"},
        "scenario_type": "cross_cutting",
    },

    # --- Category D: Compositional novelty ---
    {
        "text": "Our enterprise customer with a premium support contract is experiencing critical downtime",
        "context": Context(
            user_role="customer",
            task_type="escalation",
            domain="customer_service",
            tags=["agent-0", "dept-escalation"],
        ),
        "expected_semantic_ids": {"semantic-premium-escalation"},
        "scenario_type": "compositional",
    },
    {
        "text": "Customer claims they were charged in violation of consumer protection regulations",
        "context": Context(
            user_role="customer",
            task_type="compliance",
            domain="customer_service",
            tags=["agent-0", "dept-compliance"],
        ),
        "expected_semantic_ids": {"semantic-compliance-billing"},
        "scenario_type": "compositional",
    },
    {
        "text": "Customer was billed full price during the three days our servers were completely down",
        "context": Context(
            user_role="customer",
            task_type="billing",
            domain="customer_service",
            tags=["agent-0", "dept-billing"],
        ),
        "expected_semantic_ids": {"semantic-technical-billing"},
        "scenario_type": "compositional",
    },
]


# ---------------------------------------------------------------------------
# Novel department injection
# ---------------------------------------------------------------------------

FRAUD_CONSTRAINTS = [
    "Immediately freeze the account when fraud indicators are detected and notify the security team.",
    "Verify the customer's identity through two-factor authentication before discussing fraud claims.",
    "Document all fraud investigation steps in the incident tracking system with timestamps.",
]


def add_novel_department(corpus: Corpus) -> list[str]:
    """Add a 'fraud' department to the corpus.  Returns new instruction IDs."""
    new_ids = []
    for j, content in enumerate(FRAUD_CONSTRAINTS):
        inst_id = f"dept-fraud-constraint-{j}"
        corpus.add(Instruction(
            id=inst_id,
            type=InstructionType.CONSTRAINT,
            priority=85,
            content=content,
            scope=ScopeCondition(required_tags=["dept-fraud"]),
            tags=["dept-fraud"],
        ))
        new_ids.append(inst_id)
    return new_ids


def add_semantic_instructions(corpus: Corpus) -> list[str]:
    """Add semantically-discoverable instructions to the corpus.

    These instructions have NO required_tags, NO mandatory tags, and scopes
    with task_types that don't match standard query contexts.  They can ONLY
    be discovered through vector similarity search.

    Returns the list of new instruction IDs.
    """
    new_ids: list[str] = []
    for spec in SEMANTIC_INSTRUCTIONS:
        corpus.add(Instruction(
            id=spec["id"],
            type=spec["type"],
            priority=spec["priority"],
            content=spec["content"],
            scope=spec["scope"],
            tags=spec["tags"],
        ))
        new_ids.append(spec["id"])
    return new_ids


def generate_semantic_queries() -> list[tuple[str, Context, set[str], str]]:
    """Generate queries designed to test semantic retrieval.

    Returns list of (query_text, context, expected_semantic_ids, scenario_type).

    ``expected_semantic_ids`` contains ONLY the semantic instruction IDs that
    should be found — standard instructions (safety, global, dept, persona) are
    excluded from this metric.
    """
    return [
        (spec["text"], spec["context"], spec["expected_semantic_ids"],
         spec["scenario_type"])
        for spec in SEMANTIC_QUERIES
    ]


# ---------------------------------------------------------------------------
# Novel context query generation
# ---------------------------------------------------------------------------

def generate_novel_queries(
    num_agents: int,
    metadata: dict,
) -> list[tuple[str, Context, set[str], str]]:
    """Generate queries with contexts NOT anticipated by CPA wiring.

    Returns list of (query_text, context, expected_ids, novel_type).
    """
    safety_ids = {f"safety-{i}" for i in range(len(SAFETY_CONTENTS))}
    global_ids = {f"global-policy-{i}" for i in range(len(GLOBAL_POLICY_TOPICS))}
    queries: list[tuple[str, Context, set[str], str]] = []

    # --- Type 1: Unknown department ("fraud") ---
    # CPA has no lookup for "fraud"; returns safety+global only.
    # BEAR retrieves fraud instructions via required_tags match.
    fraud_ids = {f"dept-fraud-constraint-{j}" for j in range(len(FRAUD_CONSTRAINTS))}
    fraud_query_texts = [
        "Customer reporting a suspicious fraudulent transaction on their account",
        "Investigate potential identity theft and unauthorized account access",
        "Flag this transaction as potentially fraudulent and freeze the account",
        "Multiple unauthorized charges appeared overnight on a customer's card",
        "Customer claims someone opened accounts in their name without consent",
        "Detect and block a pattern of small test charges preceding a large fraud attempt",
        "Wire transfer to an unrecognized overseas account needs immediate review",
    ]
    for q in fraud_query_texts:
        ctx = Context(
            user_role="customer",
            task_type="fraud",
            domain="customer_service",
            tags=[f"agent-{num_agents}", "dept-fraud"],
        )
        expected = safety_ids | global_ids | fraud_ids
        queries.append((q, ctx, expected, "unknown_dept"))

    # --- Type 2: Cross-department (billing + returns) ---
    # Context carries two dept tags.  BEAR's required_tags gate passes for both.
    # CPA looks up only the first department.
    billing_ids = {f"dept-billing-constraint-{j}" for j in range(3)}
    returns_ids = {f"dept-returns-constraint-{j}" for j in range(3)}
    cross_query_texts = [
        "Customer received a damaged item and was also overcharged on the invoice",
        "Need to process both a return and a billing adjustment for the same order",
        "The return was processed but the refund never appeared on the billing statement",
        "Item arrived broken and the replacement was billed at the wrong price",
        "Customer wants to return an item but disputes the restocking fee on the invoice",
        "Refund was issued for the return but applied to the wrong billing account",
        "Exchange request requires both a return label and a billing credit adjustment",
    ]
    for q in cross_query_texts:
        ctx = Context(
            user_role="customer",
            task_type="billing",
            domain="customer_service",
            tags=["agent-0", "dept-billing", "dept-returns"],
        )
        expected = safety_ids | global_ids | billing_ids | returns_ids | {"persona-agent-0"}
        queries.append((q, ctx, expected, "cross_dept"))

    # --- Type 3: Unseen modifier (urgent / VIP) ---
    # CPA ignores these tags entirely.
    modifier_query_texts = [
        "URGENT: Customer threatening legal action over unresolved billing dispute",
        "VIP customer escalation: premium account holder demanding immediate resolution",
        "CRITICAL: System flagged this account for regulatory compliance review",
        "HIGH PRIORITY: Customer filed a complaint with the consumer protection bureau",
        "ESCALATED: Third attempt to resolve billing error with no progress",
    ]
    for q in modifier_query_texts:
        ctx = Context(
            user_role="customer",
            task_type="billing",
            domain="customer_service",
            tags=["agent-0", "dept-billing", "urgent", "vip"],
        )
        expected = safety_ids | global_ids | billing_ids | {"persona-agent-0"}
        queries.append((q, ctx, expected, "unseen_modifier"))

    # --- Type 4: Conflict scenario ---
    # Agent in billing dept with "discount" tag.  Both conflict instructions
    # have required_tags matching billing dept.  BEAR resolves (keeps higher
    # priority); CPA includes the one it finds without resolution.
    num_departments = metadata["num_departments"]
    if num_departments >= 2:
        conflict_query_texts = [
            "Customer asking for a discount on their billing charges",
            "Can I get a price reduction on my current subscription?",
            "Apply a loyalty discount to offset the billing increase",
            "Manager authorized a one-time courtesy credit on the invoice",
            "Customer wants to negotiate a lower rate for the renewal billing",
        ]
        for q in conflict_query_texts:
            ctx = Context(
                user_role="customer",
                task_type="billing",
                domain="customer_service",
                tags=["agent-0", "dept-billing", "discount"],
            )
            expected = (
                safety_ids | global_ids | billing_ids
                | {"persona-agent-0", "conflict-billing-offer-discount"}
            )
            queries.append((q, ctx, expected, "conflict"))

    return queries


# ---------------------------------------------------------------------------
# Conflict pair detection
# ---------------------------------------------------------------------------

def count_unresolved_conflicts(retrieved: list[ScoredInstruction]) -> int:
    """Count instruction pairs where both sides of a conflict are present."""
    ids = {r.instruction.id for r in retrieved}
    conflicts = 0
    seen_pairs: set[tuple[str, str]] = set()
    for r in retrieved:
        for cid in r.instruction.conflicts_with:
            if cid in ids:
                pair = tuple(sorted([r.instruction.id, cid]))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    conflicts += 1
    return conflicts


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ComparisonResult:
    num_agents: int = 0
    total_instructions: int = 0
    num_queries: int = 0
    # --- BEAR standard metrics ---
    bear_persona_recall: float = 0.0
    bear_dept_recall: float = 0.0
    bear_safety_recall: float = 0.0
    bear_global_recall: float = 0.0
    bear_scope_violations: int = 0
    bear_cross_dept: float = 0.0
    bear_mean_tokens: float = 0.0
    bear_mean_latency_ms: float = 0.0
    # --- CPA standard metrics ---
    cpa_persona_recall: float = 0.0
    cpa_dept_recall: float = 0.0
    cpa_safety_recall: float = 0.0
    cpa_global_recall: float = 0.0
    cpa_scope_violations: int = 0
    cpa_cross_dept: float = 0.0
    cpa_mean_tokens: float = 0.0
    cpa_mean_latency_ms: float = 0.0
    # --- Authoring burden ---
    cpa_wiring_lines: int = 0
    cpa_num_lookup_tables: int = 0
    # --- Novel context ---
    bear_novel_recall: float = 0.0
    cpa_novel_recall: float = 0.0
    num_novel_queries: int = 0
    novel_fisher_p: float = 1.0
    # --- Novel by type ---
    novel_by_type: dict = field(default_factory=dict)
    # --- Conflict resolution ---
    bear_unresolved_conflicts: int = 0
    cpa_unresolved_conflicts: int = 0
    # --- Token efficiency ---
    static_tokens: int = 0
    bear_token_ratio: float = 0.0
    cpa_token_ratio: float = 0.0
    # --- Semantic retrieval advantage (Phase 3) ---
    bear_semantic_recall: float = 0.0
    cpa_semantic_recall: float = 0.0
    num_semantic_queries: int = 0
    semantic_by_type: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------

def run_evaluation(use_hash: bool = False):
    model = "hash" if use_hash else EMBEDDING_MODEL
    print(f"Embedding model: {model}")
    print(f"Comparison: BEAR retrieval pipeline vs Conditional Prompt Assembly (CPA)")

    results: list[ComparisonResult] = []
    composer = Composer(strategy=CompositionStrategy.HIERARCHICAL)

    for num_agents in SCALE_POINTS:
        print(f"\n{'=' * 70}")
        print(f"  Scale point: {num_agents} agents")
        print(f"{'=' * 70}")

        # --- Shared corpus ---
        corpus, meta = generate_corpus(num_agents)
        total_instr = meta["total_instructions"]
        print(f"  Corpus: {total_instr} instructions, {meta['num_departments']} departments")

        # --- BEAR setup ---
        config = Config(
            embedding_model=model,
            embedding_backend=EmbeddingBackend.NUMPY,
            priority_weight=PRIORITY_WEIGHT,
            default_threshold=THRESHOLD,
            default_top_k=TOP_K,
            mandatory_tags=["safety", "global"],
        )
        retriever = Retriever(corpus, config=config)
        retriever.build_index()

        # --- CPA setup ---
        cpa = ConditionalPromptAssembler(corpus, meta)

        # --- Static baseline ---
        static_tok = compute_static_tokens(corpus)

        # --- Sample agents ---
        sample_n = min(num_agents, SAMPLE_AGENTS)
        step = max(1, num_agents // sample_n)
        sampled = list(range(0, num_agents, step))[:sample_n]

        # Accumulators — BEAR
        b_persona_h, b_persona_t = 0, 0
        b_dept_h, b_dept_t = 0, 0
        b_safety_h, b_safety_t = 0, 0
        b_global_h, b_global_t = 0, 0
        b_violations = 0
        b_cross: list[int] = []
        b_tokens: list[int] = []
        b_latencies: list[float] = []
        b_conflicts = 0

        # Accumulators — CPA
        c_persona_h, c_persona_t = 0, 0
        c_dept_h, c_dept_t = 0, 0
        c_safety_h, c_safety_t = 0, 0
        c_global_h, c_global_t = 0, 0
        c_violations = 0
        c_cross: list[int] = []
        c_tokens: list[int] = []
        c_latencies: list[float] = []
        c_conflicts = 0

        # ---- Phase 1: Standard queries ----
        for agent_idx in sampled:
            dept = meta["agents"][agent_idx]["dept_name"]
            dept_tag = f"dept-{dept}"
            persona_id = f"persona-agent-{agent_idx}"
            dept_ids = {f"dept-{dept}-constraint-{j}" for j in range(3)}
            safety_ids = {f"safety-{i}" for i in range(len(SAFETY_CONTENTS))}
            global_ids = {f"global-policy-{i}" for i in range(len(GLOBAL_POLICY_TOPICS))}

            for query_text, ctx in generate_queries(agent_idx, dept):
                # === BEAR ===
                t0 = time.perf_counter()
                bear_ret = retriever.retrieve(query_text, ctx, top_k=TOP_K)
                b_latencies.append((time.perf_counter() - t0) * 1000)
                br_ids = {r.id for r in bear_ret}

                b_persona_t += 1
                if persona_id in br_ids:
                    b_persona_h += 1
                b_dept_t += len(dept_ids)
                b_dept_h += len(dept_ids & br_ids)
                b_safety_t += len(safety_ids)
                b_safety_h += len(safety_ids & br_ids)
                b_global_t += len(global_ids)
                b_global_h += len(global_ids & br_ids)
                b_violations += count_scope_violations(bear_ret, agent_idx)
                cross_b = 0
                for r in bear_ret:
                    for t in r.instruction.tags:
                        if t.startswith("dept-") and t != dept_tag:
                            cross_b += 1
                            break
                b_cross.append(cross_b)
                b_tokens.append(estimate_tokens(composer.compose(bear_ret)))
                b_conflicts += count_unresolved_conflicts(bear_ret)

                # === CPA ===
                t0 = time.perf_counter()
                cpa_ret = cpa.retrieve(agent_idx, dept, ctx.tags)
                c_latencies.append((time.perf_counter() - t0) * 1000)
                cr_ids = {r.instruction.id for r in cpa_ret}

                c_persona_t += 1
                if persona_id in cr_ids:
                    c_persona_h += 1
                c_dept_t += len(dept_ids)
                c_dept_h += len(dept_ids & cr_ids)
                c_safety_t += len(safety_ids)
                c_safety_h += len(safety_ids & cr_ids)
                c_global_t += len(global_ids)
                c_global_h += len(global_ids & cr_ids)
                c_violations += count_scope_violations(cpa_ret, agent_idx)
                cross_c = 0
                for r in cpa_ret:
                    for t in r.instruction.tags:
                        if t.startswith("dept-") and t != dept_tag:
                            cross_c += 1
                            break
                c_cross.append(cross_c)
                c_tokens.append(estimate_tokens(composer.compose(cpa_ret)))
                c_conflicts += count_unresolved_conflicts(cpa_ret)

        n_q = len(b_latencies)

        # ---- Phase 2: Novel context queries ----
        # Add fraud department to corpus, rebuild BEAR index.
        # CPA lookup tables remain stale (no fraud key).
        fraud_ids_added = add_novel_department(corpus)
        retriever_novel = Retriever(corpus, config=config)
        retriever_novel.build_index()

        novel_queries = generate_novel_queries(num_agents, meta)
        b_novel_h, b_novel_t = 0, 0
        c_novel_h, c_novel_t = 0, 0
        novel_by_type: dict[str, dict] = {}
        # Per-query binary outcomes for Fisher's exact test
        bear_novel_hits: list[bool] = []
        cpa_novel_hits: list[bool] = []

        for query_text, ctx, expected_ids, novel_type in novel_queries:
            # Parse agent/dept from context tags for CPA
            agent_tags = [t for t in ctx.tags if t.startswith("agent-")]
            dept_tags = [t for t in ctx.tags if t.startswith("dept-")]
            agent_idx_n = int(agent_tags[0].split("-")[1]) if agent_tags else -1
            # CPA only uses the first dept tag
            dept_name_n = dept_tags[0].replace("dept-", "", 1) if dept_tags else ""

            # BEAR (with fraud dept)
            bear_ret_n = retriever_novel.retrieve(query_text, ctx, top_k=TOP_K)
            br_ids_n = {r.id for r in bear_ret_n}
            b_hits = len(br_ids_n & expected_ids)
            b_novel_t += len(expected_ids)
            b_novel_h += b_hits

            # CPA (stale — no fraud)
            cpa_ret_n = cpa.retrieve(agent_idx_n, dept_name_n, ctx.tags)
            cr_ids_n = {r.instruction.id for r in cpa_ret_n}
            c_hits = len(cr_ids_n & expected_ids)
            c_novel_t += len(expected_ids)
            c_novel_h += c_hits

            bear_novel_hits.append(b_hits == len(expected_ids))
            cpa_novel_hits.append(c_hits == len(expected_ids))

            if novel_type not in novel_by_type:
                novel_by_type[novel_type] = {
                    "bear_hits": 0, "cpa_hits": 0, "total": 0, "count": 0,
                }
            novel_by_type[novel_type]["bear_hits"] += b_hits
            novel_by_type[novel_type]["cpa_hits"] += c_hits
            novel_by_type[novel_type]["total"] += len(expected_ids)
            novel_by_type[novel_type]["count"] += 1

        # Fisher's exact test on novel query outcomes
        from scipy.stats import fisher_exact
        # Contingency table: BEAR hit/miss × CPA hit/miss
        both_hit = sum(b and c for b, c in zip(bear_novel_hits, cpa_novel_hits))
        bear_only = sum(b and not c for b, c in zip(bear_novel_hits, cpa_novel_hits))
        cpa_only = sum(not b and c for b, c in zip(bear_novel_hits, cpa_novel_hits))
        both_miss = sum(not b and not c for b, c in zip(bear_novel_hits, cpa_novel_hits))
        contingency = [[both_hit, bear_only], [cpa_only, both_miss]]
        degenerate = (cpa_only == 0 and both_miss == 0)
        if degenerate:
            fisher_p = float('nan')
            print(f"  Novel query Fisher's test: DEGENERATE (no CPA-only or both-miss cases) "
                  f"— BEAR hits all {both_hit + bear_only} queries, "
                  f"CPA misses {bear_only}; test not applicable")
        else:
            _, fisher_p = fisher_exact(contingency, alternative="greater")
            print(f"  Novel query Fisher's exact test: p={fisher_p:.4f} "
                  f"(BEAR-only={bear_only}, CPA-only={cpa_only}, both={both_hit}, neither={both_miss})")

        # Remove fraud instructions so next scale point starts clean
        for fid in fraud_ids_added:
            corpus.remove(fid)

        # ---- Phase 3: Semantic retrieval advantage ----
        # Add instructions discoverable ONLY via embedding similarity.
        # CPA has no lookup keys for these; BEAR finds them via vector search.
        semantic_ids_added = add_semantic_instructions(corpus)
        retriever_semantic = Retriever(corpus, config=config)
        retriever_semantic.build_index()

        # Rebuild CPA too — but it silently ignores the new instructions
        # because their IDs don't match any known patterns.
        cpa_semantic = ConditionalPromptAssembler(corpus, meta)

        semantic_queries = generate_semantic_queries()
        b_sem_h, b_sem_t = 0, 0
        c_sem_h, c_sem_t = 0, 0
        semantic_by_type: dict[str, dict] = {}

        for query_text, ctx, expected_sem_ids, sem_type in semantic_queries:
            # Parse agent/dept from context for CPA
            agent_tags = [t for t in ctx.tags if t.startswith("agent-")]
            dept_tags = [t for t in ctx.tags if t.startswith("dept-")]
            agent_idx_s = int(agent_tags[0].split("-")[1]) if agent_tags else 0
            dept_name_s = dept_tags[0].replace("dept-", "", 1) if dept_tags else ""

            # BEAR retrieval
            bear_ret_s = retriever_semantic.retrieve(query_text, ctx, top_k=TOP_K)
            br_ids_s = {r.id for r in bear_ret_s}
            b_hits = len(br_ids_s & expected_sem_ids)
            b_sem_t += len(expected_sem_ids)
            b_sem_h += b_hits

            # CPA retrieval
            cpa_ret_s = cpa_semantic.retrieve(agent_idx_s, dept_name_s, ctx.tags)
            cr_ids_s = {r.instruction.id for r in cpa_ret_s}
            c_hits = len(cr_ids_s & expected_sem_ids)
            c_sem_t += len(expected_sem_ids)
            c_sem_h += c_hits

            if sem_type not in semantic_by_type:
                semantic_by_type[sem_type] = {
                    "bear_hits": 0, "cpa_hits": 0, "total": 0, "count": 0,
                }
            semantic_by_type[sem_type]["bear_hits"] += b_hits
            semantic_by_type[sem_type]["cpa_hits"] += c_hits
            semantic_by_type[sem_type]["total"] += len(expected_sem_ids)
            semantic_by_type[sem_type]["count"] += 1

        # Remove semantic instructions for next scale point
        for sid in semantic_ids_added:
            corpus.remove(sid)

        # ---- Assemble result ----
        bear_mean_tok = sum(b_tokens) / n_q if n_q else 0
        cpa_mean_tok = sum(c_tokens) / n_q if n_q else 0

        res = ComparisonResult(
            num_agents=num_agents,
            total_instructions=total_instr,
            num_queries=n_q,
            # BEAR
            bear_persona_recall=b_persona_h / b_persona_t if b_persona_t else 0,
            bear_dept_recall=b_dept_h / b_dept_t if b_dept_t else 0,
            bear_safety_recall=b_safety_h / b_safety_t if b_safety_t else 0,
            bear_global_recall=b_global_h / b_global_t if b_global_t else 0,
            bear_scope_violations=b_violations,
            bear_cross_dept=sum(b_cross) / n_q if n_q else 0,
            bear_mean_tokens=bear_mean_tok,
            bear_mean_latency_ms=sum(b_latencies) / n_q if n_q else 0,
            # CPA
            cpa_persona_recall=c_persona_h / c_persona_t if c_persona_t else 0,
            cpa_dept_recall=c_dept_h / c_dept_t if c_dept_t else 0,
            cpa_safety_recall=c_safety_h / c_safety_t if c_safety_t else 0,
            cpa_global_recall=c_global_h / c_global_t if c_global_t else 0,
            cpa_scope_violations=c_violations,
            cpa_cross_dept=sum(c_cross) / n_q if n_q else 0,
            cpa_mean_tokens=cpa_mean_tok,
            cpa_mean_latency_ms=sum(c_latencies) / n_q if n_q else 0,
            # Authoring
            cpa_wiring_lines=cpa.wiring_lines,
            cpa_num_lookup_tables=cpa.num_lookup_tables,
            # Novel
            bear_novel_recall=b_novel_h / b_novel_t if b_novel_t else 0,
            cpa_novel_recall=c_novel_h / c_novel_t if c_novel_t else 0,
            num_novel_queries=len(novel_queries),
            novel_fisher_p=round(float(fisher_p), 4) if not degenerate else None,
            novel_by_type=novel_by_type,
            # Conflicts
            bear_unresolved_conflicts=b_conflicts,
            cpa_unresolved_conflicts=c_conflicts,
            # Tokens
            static_tokens=static_tok,
            bear_token_ratio=bear_mean_tok / static_tok if static_tok else 0,
            cpa_token_ratio=cpa_mean_tok / static_tok if static_tok else 0,
            # Semantic
            bear_semantic_recall=b_sem_h / b_sem_t if b_sem_t else 0,
            cpa_semantic_recall=c_sem_h / c_sem_t if c_sem_t else 0,
            num_semantic_queries=len(semantic_queries),
            semantic_by_type=semantic_by_type,
        )
        results.append(res)

        # Bootstrap CIs on per-query token distributions
        from stat_utils import bootstrap_ci, format_ci
        ci_bear_tok = bootstrap_ci(b_tokens)
        ci_cpa_tok = bootstrap_ci(c_tokens)

        # Per-scale summary
        print(f"  Standard queries: {n_q}")
        print(f"  BEAR  persona/dept/safety/global: "
              f"{res.bear_persona_recall:.3f} / {res.bear_dept_recall:.3f} / "
              f"{res.bear_safety_recall:.3f} / {res.bear_global_recall:.3f}")
        print(f"  CPA   persona/dept/safety/global: "
              f"{res.cpa_persona_recall:.3f} / {res.cpa_dept_recall:.3f} / "
              f"{res.cpa_safety_recall:.3f} / {res.cpa_global_recall:.3f}")
        print(f"  Tokens/query: BEAR={format_ci(ci_bear_tok, precision=0)}  "
              f"CPA={format_ci(ci_cpa_tok, precision=0)}  Static={res.static_tokens}")
        print(f"  Novel recall: BEAR={res.bear_novel_recall:.3f}  "
              f"CPA={res.cpa_novel_recall:.3f}  ({res.num_novel_queries} queries)"
              f"  Fisher's p={res.novel_fisher_p}")
        print(f"  Unresolved conflicts: BEAR={res.bear_unresolved_conflicts}  "
              f"CPA={res.cpa_unresolved_conflicts}")
        print(f"  Semantic recall: BEAR={res.bear_semantic_recall:.3f}  "
              f"CPA={res.cpa_semantic_recall:.3f}  ({res.num_semantic_queries} queries)")
        print(f"  CPA wiring: {res.cpa_wiring_lines} lines, "
              f"{res.cpa_num_lookup_tables} lookup tables")

    print_summary(results)
    print_latex_tables(results)
    write_csv(results)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_summary(results: list[ComparisonResult]):
    print(f"\n{'=' * 90}")
    print("  SUMMARY: BEAR vs Conditional Prompt Assembly")
    print(f"{'=' * 90}")

    # Table 1: Standard query correctness
    print("\n--- Standard Query Recall ---")
    hdr = f"{'N':>5} {'Instr':>5}  {'BEAR P':>7} {'CPA P':>7}  " \
          f"{'BEAR D':>7} {'CPA D':>7}  {'BEAR S':>7} {'CPA S':>7}  " \
          f"{'BEAR G':>7} {'CPA G':>7}"
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        print(f"{r.num_agents:>5} {r.total_instructions:>5}  "
              f"{r.bear_persona_recall:>7.3f} {r.cpa_persona_recall:>7.3f}  "
              f"{r.bear_dept_recall:>7.3f} {r.cpa_dept_recall:>7.3f}  "
              f"{r.bear_safety_recall:>7.3f} {r.cpa_safety_recall:>7.3f}  "
              f"{r.bear_global_recall:>7.3f} {r.cpa_global_recall:>7.3f}")

    # Table 2: Novel context
    print("\n--- Novel Context Recall ---")
    hdr2 = f"{'N':>5}  {'BEAR':>7} {'CPA':>7}  {'Delta':>7}"
    print(hdr2)
    print("-" * len(hdr2))
    for r in results:
        delta = r.bear_novel_recall - r.cpa_novel_recall
        print(f"{r.num_agents:>5}  {r.bear_novel_recall:>7.3f} "
              f"{r.cpa_novel_recall:>7.3f}  {delta:>+7.3f}")

    # Table 3: Semantic retrieval advantage
    print("\n--- Semantic Retrieval Advantage ---")
    hdr3 = f"{'N':>5}  {'BEAR':>7} {'CPA':>7}  {'Delta':>7}"
    print(hdr3)
    print("-" * len(hdr3))
    for r in results:
        delta = r.bear_semantic_recall - r.cpa_semantic_recall
        print(f"{r.num_agents:>5}  {r.bear_semantic_recall:>7.3f} "
              f"{r.cpa_semantic_recall:>7.3f}  {delta:>+7.3f}")

    # Table 4: Token efficiency
    print("\n--- Token Efficiency ---")
    hdr4 = f"{'N':>5}  {'BEAR':>6} {'CPA':>6} {'Static':>7}  " \
           f"{'B/S':>6} {'C/S':>6}  {'CPA Lines':>10}"
    print(hdr4)
    print("-" * len(hdr4))
    for r in results:
        print(f"{r.num_agents:>5}  {r.bear_mean_tokens:>6.0f} "
              f"{r.cpa_mean_tokens:>6.0f} {r.static_tokens:>7}  "
              f"{r.bear_token_ratio:>6.3f} {r.cpa_token_ratio:>6.3f}  "
              f"{r.cpa_wiring_lines:>10}")


def print_latex_tables(results: list[ComparisonResult]):
    print("\n" + "=" * 70)
    print("  LaTeX Tables")
    print("=" * 70)

    # Table 1: Correctness comparison
    print(r"""
\begin{table}[t]
\caption{Behavioral identity recall: BEAR vs.\ Conditional Prompt Assembly (CPA).
Both systems access identical instruction content; CPA uses deterministic lookup tables
while BEAR uses semantic retrieval with scope filtering.
CPA achieves perfect recall on anticipated contexts but cannot adapt to novel situations.}
\label{tab:baseline-correctness}
\begin{tabular}{@{}rr cccc cccc@{}}
\toprule
& & \multicolumn{4}{c}{BEAR} & \multicolumn{4}{c}{CPA} \\
\cmidrule(lr){3-6}\cmidrule(lr){7-10}
$N$ & Instr & Pers & Dept & Safe & Glob & Pers & Dept & Safe & Glob \\
\midrule""")
    for r in results:
        print(f"{r.num_agents} & {r.total_instructions} & "
              f"{r.bear_persona_recall:.3f} & {r.bear_dept_recall:.3f} & "
              f"{r.bear_safety_recall:.3f} & {r.bear_global_recall:.3f} & "
              f"{r.cpa_persona_recall:.3f} & {r.cpa_dept_recall:.3f} & "
              f"{r.cpa_safety_recall:.3f} & {r.cpa_global_recall:.3f} \\\\")
    print(r"""\bottomrule
\end{tabular}
\end{table}""")

    # Table 2: Novel context adaptability
    print(r"""
\begin{table}[t]
\caption{Adaptability: recall on novel context queries not anticipated by CPA wiring.
BEAR's semantic retrieval adapts to new departments, cross-department queries,
and unseen context modifiers, while CPA returns only base instructions.}
\label{tab:baseline-adaptability}
\begin{tabular}{@{}rr cc c r@{}}
\toprule
$N$ & Novel $Q$ & BEAR & CPA & $\Delta$ & CPA Lines \\
\midrule""")
    for r in results:
        delta = r.bear_novel_recall - r.cpa_novel_recall
        print(f"{r.num_agents} & {r.num_novel_queries} & "
              f"{r.bear_novel_recall:.3f} & {r.cpa_novel_recall:.3f} & "
              f"{delta:+.3f} & {r.cpa_wiring_lines} \\\\")
    print(r"""\bottomrule
\end{tabular}
\end{table}""")

    # Table 3: Token efficiency
    print(r"""
\begin{table}[t]
\caption{Token efficiency: BEAR and CPA both achieve dramatic reduction
over static prompting (all instructions). CPA is slightly more compact
since it performs exact lookup with no semantic over-retrieval.}
\label{tab:baseline-tokens}
\begin{tabular}{@{}rr rrr cc@{}}
\toprule
$N$ & Instr & BEAR & CPA & Static & BEAR/S & CPA/S \\
\midrule""")
    for r in results:
        print(f"{r.num_agents} & {r.total_instructions} & "
              f"{r.bear_mean_tokens:.0f} & {r.cpa_mean_tokens:.0f} & "
              f"{r.static_tokens:,} & "
              f"{r.bear_token_ratio:.3f} & {r.cpa_token_ratio:.3f} \\\\")
    print(r"""\bottomrule
\end{tabular}
\end{table}""")

    # Novel breakdown by type (for the last scale point)
    last = results[-1]
    if last.novel_by_type:
        print(r"""
\begin{table}[t]
\caption{Novel context recall breakdown by query type at $N=500$.
BEAR adapts to every novel scenario; CPA fails on unknown departments
and cross-department queries.}
\label{tab:baseline-novel-breakdown}
\begin{tabular}{@{}l r ccc@{}}
\toprule
Query Type & Count & BEAR & CPA & $\Delta$ \\
\midrule""")
        type_labels = {
            "unknown_dept": "Unknown department",
            "cross_dept": "Cross-department",
            "unseen_modifier": "Unseen modifier",
            "conflict": "Conflict resolution",
        }
        for ntype in ["unknown_dept", "cross_dept", "unseen_modifier", "conflict"]:
            if ntype in last.novel_by_type:
                d = last.novel_by_type[ntype]
                br = d["bear_hits"] / d["total"] if d["total"] else 0
                cr = d["cpa_hits"] / d["total"] if d["total"] else 0
                label = type_labels.get(ntype, ntype)
                print(f"{label} & {d['count']} & {br:.3f} & {cr:.3f} & "
                      f"{br - cr:+.3f} \\\\")
        print(r"""\bottomrule
\end{tabular}
\end{table}""")

    # Table 5: Semantic retrieval advantage
    print(r"""
\begin{table}[t]
\caption{Semantic retrieval advantage: recall on instructions discoverable
only through embedding similarity. These instructions have no explicit tags
matching query contexts; CPA's lookup tables cannot reference them.
BEAR finds them through vector similarity search ($\theta=0.3$).}
\label{tab:semantic-advantage}
\begin{tabular}{@{}rr cc c@{}}
\toprule
$N$ & Semantic $Q$ & BEAR & CPA & $\Delta$ \\
\midrule""")
    for r in results:
        delta = r.bear_semantic_recall - r.cpa_semantic_recall
        print(f"{r.num_agents} & {r.num_semantic_queries} & "
              f"{r.bear_semantic_recall:.3f} & {r.cpa_semantic_recall:.3f} & "
              f"{delta:+.3f} \\\\")
    print(r"""\bottomrule
\end{tabular}
\end{table}""")

    # Table 6: Semantic breakdown by scenario type (last scale point)
    if last.semantic_by_type:
        print(r"""
\begin{table}[t]
\caption{Semantic recall breakdown by scenario type at $N=500$.
BEAR's embedding-based retrieval discovers contextually relevant instructions
across all categories; CPA achieves zero recall because its lookup tables
have no entries for these instruction types.}
\label{tab:semantic-breakdown}
\begin{tabular}{@{}l r ccc@{}}
\toprule
Scenario Type & Count & BEAR & CPA & $\Delta$ \\
\midrule""")
        sem_type_labels = {
            "semantically_scoped": "Semantically scoped",
            "paraphrased_query": "Paraphrased query",
            "cross_cutting": "Cross-cutting concern",
            "compositional": "Compositional novelty",
        }
        for stype in ["semantically_scoped", "paraphrased_query",
                       "cross_cutting", "compositional"]:
            if stype in last.semantic_by_type:
                d = last.semantic_by_type[stype]
                br = d["bear_hits"] / d["total"] if d["total"] else 0
                cr = d["cpa_hits"] / d["total"] if d["total"] else 0
                label = sem_type_labels.get(stype, stype)
                print(f"{label} & {d['count']} & {br:.3f} & {cr:.3f} & "
                      f"{br - cr:+.3f} \\\\")
        print(r"""\bottomrule
\end{tabular}
\end{table}""")


def write_csv(results: list[ComparisonResult]):
    csv_path = project_root / "results" / "baseline_comparison_results.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "num_agents", "total_instructions", "num_queries",
            "bear_persona_recall", "bear_dept_recall",
            "bear_safety_recall", "bear_global_recall",
            "bear_scope_violations", "bear_cross_dept",
            "bear_mean_tokens", "bear_mean_latency_ms",
            "cpa_persona_recall", "cpa_dept_recall",
            "cpa_safety_recall", "cpa_global_recall",
            "cpa_scope_violations", "cpa_cross_dept",
            "cpa_mean_tokens", "cpa_mean_latency_ms",
            "cpa_wiring_lines",
            "bear_novel_recall", "cpa_novel_recall",
            "num_novel_queries",
            "bear_unresolved_conflicts", "cpa_unresolved_conflicts",
            "static_tokens", "bear_token_ratio", "cpa_token_ratio",
            "bear_semantic_recall", "cpa_semantic_recall",
            "num_semantic_queries",
        ])
        for r in results:
            writer.writerow([
                r.num_agents, r.total_instructions, r.num_queries,
                f"{r.bear_persona_recall:.4f}", f"{r.bear_dept_recall:.4f}",
                f"{r.bear_safety_recall:.4f}", f"{r.bear_global_recall:.4f}",
                r.bear_scope_violations, f"{r.bear_cross_dept:.2f}",
                f"{r.bear_mean_tokens:.0f}", f"{r.bear_mean_latency_ms:.2f}",
                f"{r.cpa_persona_recall:.4f}", f"{r.cpa_dept_recall:.4f}",
                f"{r.cpa_safety_recall:.4f}", f"{r.cpa_global_recall:.4f}",
                r.cpa_scope_violations, f"{r.cpa_cross_dept:.2f}",
                f"{r.cpa_mean_tokens:.0f}", f"{r.cpa_mean_latency_ms:.2f}",
                r.cpa_wiring_lines,
                f"{r.bear_novel_recall:.4f}", f"{r.cpa_novel_recall:.4f}",
                r.num_novel_queries,
                r.bear_unresolved_conflicts, r.cpa_unresolved_conflicts,
                r.static_tokens,
                f"{r.bear_token_ratio:.4f}", f"{r.cpa_token_ratio:.4f}",
                f"{r.bear_semantic_recall:.4f}", f"{r.cpa_semantic_recall:.4f}",
                r.num_semantic_queries,
            ])
    print(f"\nCSV written to {csv_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="BEAR vs Conditional Prompt Assembly baseline comparison")
    parser.add_argument("--hash", action="store_true",
                        help="Use deterministic hash embeddings instead of "
                             "sentence-transformers")
    args = parser.parse_args()
    run_evaluation(use_hash=args.hash)
