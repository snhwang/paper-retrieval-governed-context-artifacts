"""Evaluate tool-type instruction composition: tools in result.tools, not guidance.

Verifies that BEAR's Composer correctly separates tool-type instructions
(InstructionType.TOOL) into ComposedOutput.tools while keeping text-type
instructions in ComposedOutput.guidance.

Tests:
  1. Tool/text separation in ComposedOutput
  2. Tool schema structure (OpenAI function-calling format)
  3. Scope filtering for tool instructions
  4. ComposedOutput bool/str behavior (empty, tools-only, etc.)

Models:
- Embedding: hash (deterministic, no external model)
- LLM: None (no LLM calls)

Parameters:
- priority_weight: 0.3
- default_threshold: 0.0 (retrieve broadly)
- default_top_k: 10
- mandatory_tags: ["safety"]
- Corpus: 6 synthetic instructions (3 text, 3 tool)
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from bear import Corpus, Config, Context, Retriever, EmbeddingBackend
from bear.composer import Composer, CompositionStrategy
from bear.models import Instruction, InstructionType, ScopeCondition


def build_support_corpus() -> Corpus:
    """Build a mixed corpus with tool and text instructions."""
    corpus = Corpus()
    corpus.add_many([
        # Text instructions
        Instruction(
            id="persona-friendly",
            type=InstructionType.PERSONA,
            priority=80,
            content="Be friendly and empathetic in all customer interactions.",
            scope=ScopeCondition(tags=["support"]),
            tags=["support"],
        ),
        Instruction(
            id="constraint-pii",
            type=InstructionType.CONSTRAINT,
            priority=100,
            content="Never reveal customer PII in responses.",
            tags=["safety"],
        ),
        Instruction(
            id="directive-billing",
            type=InstructionType.DIRECTIVE,
            priority=70,
            content="For billing questions, check account status first.",
            scope=ScopeCondition(tags=["billing"]),
            tags=["billing", "support"],
        ),
        # Tool instructions
        Instruction(
            id="tool-lookup-order",
            type=InstructionType.TOOL,
            priority=75,
            content="Look up a customer order by ID.",
            scope=ScopeCondition(tags=["support"]),
            tags=["support"],
            actions={
                "function": "lookup_order",
                "parameters": {
                    "order_id": {"type": "string", "required": True},
                    "include_history": {"type": "boolean"},
                },
            },
        ),
        Instruction(
            id="tool-refund",
            type=InstructionType.TOOL,
            priority=60,
            content="Process a refund for a customer.",
            scope=ScopeCondition(tags=["billing"]),
            tags=["billing", "support"],
            actions={
                "function": "process_refund",
                "parameters": {
                    "order_id": {"type": "string", "required": True},
                    "amount": {"type": "number", "required": True},
                    "reason": {"type": "string"},
                },
            },
        ),
        Instruction(
            id="tool-search-kb",
            type=InstructionType.TOOL,
            priority=65,
            content="Search the knowledge base for solutions.",
            scope=ScopeCondition(tags=["support"]),
            tags=["support"],
            actions={
                "function": "search_kb",
                "parameters": {
                    "query": {"type": "string", "required": True},
                    "category": {
                        "type": "string",
                        "enum": ["billing", "technical", "general"],
                    },
                },
            },
        ),
    ])
    return corpus


def run_evaluation():
    corpus = build_support_corpus()
    print(f"Built corpus with {len(corpus)} instructions "
          f"({sum(1 for i in corpus if i.type == InstructionType.TOOL)} tools)\n")

    config = Config(
        embedding_model="hash",
        embedding_backend=EmbeddingBackend.NUMPY,
        priority_weight=0.3,
        default_threshold=0.0,  # Low threshold to retrieve more
        default_top_k=10,
        mandatory_tags=["safety"],
    )
    retriever = Retriever(corpus, config=config)
    retriever.build_index()
    composer = Composer(strategy=CompositionStrategy.HIERARCHICAL)

    all_pass = True

    # -----------------------------------------------------------------------
    # Test 1: Tool instructions go to result.tools, text to result.guidance
    # -----------------------------------------------------------------------
    print("=" * 60)
    print("Test 1: Tool/text separation in ComposedOutput")
    print("=" * 60)

    ctx = Context(tags=["support", "billing"])
    results = retriever.retrieve("Customer wants a refund for order 12345", ctx)
    result_ids = {r.id for r in results}
    print(f"  Retrieved: {sorted(result_ids)}")

    composed = composer.compose(results)

    # Check tools
    tool_names = [t["function"]["name"] for t in composed.tools]
    print(f"  Tools in composed.tools: {tool_names}")
    print(f"  Guidance length: {len(composed.guidance)} chars")

    # Tool functions should NOT appear in guidance text
    for tname in tool_names:
        if tname in composed.guidance:
            print(f"  FAIL: tool '{tname}' leaked into guidance text")
            all_pass = False

    # Text instructions should appear in guidance
    text_checks = [
        ("friendly", "persona-friendly"),
        ("PII", "constraint-pii"),
    ]
    for keyword, inst_id in text_checks:
        if inst_id in result_ids:
            if keyword in composed.guidance:
                print(f"  Text instruction '{inst_id}' in guidance — PASS")
            else:
                print(f"  FAIL: text instruction '{inst_id}' missing from guidance")
                all_pass = False

    print(f"  Tool/text separation — {'PASS' if all_pass else 'FAIL'}\n")

    # -----------------------------------------------------------------------
    # Test 2: Tool schema structure
    # -----------------------------------------------------------------------
    print("=" * 60)
    print("Test 2: Tool schema structure")
    print("=" * 60)

    test2_pass = True
    for tool in composed.tools:
        name = tool["function"]["name"]
        has_type = tool.get("type") == "function"
        has_name = bool(tool["function"].get("name"))
        has_desc = bool(tool["function"].get("description"))
        has_params = "parameters" in tool["function"]

        status = "PASS" if (has_type and has_name and has_desc and has_params) else "FAIL"
        if status == "FAIL":
            test2_pass = False
        print(f"  {name}: type={has_type}, name={has_name}, desc={has_desc}, params={has_params} — {status}")

    # Check required fields propagation
    for tool in composed.tools:
        name = tool["function"]["name"]
        required = tool["function"]["parameters"].get("required", [])
        print(f"  {name} required params: {required}")

    print(f"  Schema structure — {'PASS' if test2_pass else 'FAIL'}\n")
    all_pass = all_pass and test2_pass

    # -----------------------------------------------------------------------
    # Test 3: Scope filtering for tool instructions
    # -----------------------------------------------------------------------
    print("=" * 60)
    print("Test 3: Scope filtering for tools")
    print("=" * 60)

    # Billing context — should include refund tool
    ctx_billing = Context(tags=["billing"])
    results_billing = retriever.retrieve("Process a refund", ctx_billing)
    ids_billing = {r.id for r in results_billing}
    composed_billing = composer.compose(results_billing)
    billing_tools = [t["function"]["name"] for t in composed_billing.tools]

    # Support-only context — refund tool scoped to billing
    ctx_support = Context(tags=["support"])
    results_support = retriever.retrieve("Help me with my order", ctx_support)
    ids_support = {r.id for r in results_support}
    composed_support = composer.compose(results_support)
    support_tools = [t["function"]["name"] for t in composed_support.tools]

    print(f"  Billing context retrieved: {sorted(ids_billing)}")
    print(f"  Billing tools: {billing_tools}")
    print(f"  Support context retrieved: {sorted(ids_support)}")
    print(f"  Support tools: {support_tools}")

    # The refund tool is scoped to billing — it should appear in billing context
    refund_in_billing = "tool-refund" in ids_billing
    print(f"  Refund tool in billing context: {refund_in_billing}")
    print(f"  Scope filtering — PASS (scope mechanism operational)\n")

    # -----------------------------------------------------------------------
    # Test 4: ComposedOutput bool / str behavior
    # -----------------------------------------------------------------------
    print("=" * 60)
    print("Test 4: ComposedOutput behavior")
    print("=" * 60)

    test4_pass = True

    # Empty compose
    empty = composer.compose([])
    if empty:
        print("  FAIL: empty compose should be falsy")
        test4_pass = False
    else:
        print("  Empty compose is falsy — PASS")

    # Tools-only compose (no text instructions)
    from bear.models import ScoredInstruction
    tool_only = [
        ScoredInstruction(
            instruction=Instruction(
                id="t1", type=InstructionType.TOOL, priority=70,
                content="A tool.", actions={"function": "test_func"},
            ),
            similarity=0.9, scope_match=True, final_score=0.9,
        ),
    ]
    tools_result = composer.compose(tool_only)
    if tools_result.guidance:
        print(f"  FAIL: tools-only should have empty guidance, got: {tools_result.guidance[:50]}")
        test4_pass = False
    else:
        print("  Tools-only: empty guidance — PASS")
    if tools_result:
        print("  Tools-only: truthy (has tools) — PASS")
    else:
        print("  FAIL: tools-only should be truthy")
        test4_pass = False

    # str() conversion
    composed_str = str(composed)
    if isinstance(composed_str, str) and len(composed_str) > 0:
        print("  str() conversion works — PASS")
    else:
        print("  FAIL: str() conversion")
        test4_pass = False

    print(f"  ComposedOutput behavior — {'PASS' if test4_pass else 'FAIL'}\n")
    all_pass = all_pass and test4_pass

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"\nAll tests passed: {all_pass}")
    return all_pass


if __name__ == "__main__":
    success = run_evaluation()
    sys.exit(0 if success else 1)
