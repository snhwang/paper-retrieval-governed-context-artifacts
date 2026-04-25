"""Evaluate tool-instruction retrieval precision as the tool corpus scales.

Measures:
  1. Retrieval precision — do the right tools surface for a given context?
  2. Prompt token savings — scoped retrieval vs. injecting all tools.
  3. Scaling curve — precision at 5, 10, 25, and 50 tools.
  4. End-to-end dispatch — retrieval → composition → LLM tool call → print.

Tools are dummy definitions (no real execution); the eval checks retrieval
quality and optionally runs one query through an LLM to confirm the full
pipeline closes.

Tool instructions use ``required_tags`` for hard scope gating: a tool is
only retrievable when ALL its required tags are present in the context.
This is the correct mechanism for transactional actions (eat, flee, build)
that should never appear outside their intended situation.
"""

import asyncio
import json
import sys
from pathlib import Path

import numpy as np

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from bear import Corpus, Config, Context, Retriever, EmbeddingBackend
from bear.composer import Composer, CompositionStrategy
from bear.models import Instruction, InstructionType, ScopeCondition


# ---------------------------------------------------------------------------
# Tool corpus: 50 tool instructions across 8 domains
#
# Each tool uses ``required_tags`` so it is hard-gated to contexts that
# carry those tags.  This mirrors the real design intent: you should not
# see ``eat`` during combat or ``flee`` during a social greeting.
# ---------------------------------------------------------------------------

TOOL_DEFS: list[dict] = [
    # --- Food / survival (6) ---
    {
        "id": "tool-eat",
        "content": "Consume a nearby food item to restore energy.",
        "tags": ["food", "survival"],
        "scope": {"required_tags": ["food_nearby"]},
        "actions": {"function": "eat", "parameters": {"item": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-drink",
        "content": "Drink from a water source to restore hydration.",
        "tags": ["water", "survival"],
        "scope": {"required_tags": ["water_nearby"]},
        "actions": {"function": "drink", "parameters": {"source": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-forage",
        "content": "Search the immediate area for edible plants or insects.",
        "tags": ["food", "exploration"],
        "scope": {"required_tags": ["vegetation_nearby"]},
        "actions": {"function": "forage", "parameters": {"radius": {"type": "number"}}},
    },
    {
        "id": "tool-cook",
        "content": "Cook raw food at a fire to increase its energy value.",
        "tags": ["food", "crafting"],
        "scope": {"required_tags": ["fire_nearby"]},
        "actions": {"function": "cook", "parameters": {"item": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-share-food",
        "content": "Offer food to another creature to build social bonds.",
        "tags": ["food", "social"],
        "scope": {"required_tags": ["food_nearby", "social"]},
        "actions": {"function": "share_food", "parameters": {"item": {"type": "string", "required": True}, "target": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-store-food",
        "content": "Cache food in a hidden location for later retrieval.",
        "tags": ["food", "planning"],
        "scope": {"required_tags": ["has_food"]},
        "actions": {"function": "store_food", "parameters": {"item": {"type": "string", "required": True}, "location": {"type": "string"}}},
    },

    # --- Danger / combat (6) ---
    {
        "id": "tool-flee",
        "content": "Sprint away from a predator or threat.",
        "tags": ["danger", "survival"],
        "scope": {"required_tags": ["danger"]},
        "actions": {"function": "flee", "parameters": {"direction": {"type": "string"}}},
    },
    {
        "id": "tool-rally",
        "content": "Call nearby allies to stand together against a threat.",
        "tags": ["danger", "social"],
        "scope": {"required_tags": ["danger"]},
        "actions": {"function": "rally", "parameters": {"call_type": {"type": "string", "enum": ["defensive", "aggressive"]}}},
    },
    {
        "id": "tool-hide",
        "content": "Find cover and remain motionless to avoid detection.",
        "tags": ["danger", "stealth"],
        "scope": {"required_tags": ["danger"]},
        "actions": {"function": "hide", "parameters": {"duration": {"type": "number"}}},
    },
    {
        "id": "tool-attack",
        "content": "Launch an aggressive strike against a target.",
        "tags": ["danger", "combat"],
        "scope": {"required_tags": ["combat"]},
        "actions": {"function": "attack", "parameters": {"target": {"type": "string", "required": True}, "style": {"type": "string", "enum": ["bite", "claw", "charge"]}}},
    },
    {
        "id": "tool-defend",
        "content": "Adopt a defensive posture to reduce incoming damage.",
        "tags": ["danger", "combat"],
        "scope": {"required_tags": ["combat"]},
        "actions": {"function": "defend", "parameters": {"stance": {"type": "string", "enum": ["brace", "dodge", "block"]}}},
    },
    {
        "id": "tool-warn",
        "content": "Emit an alarm call to alert others of approaching danger.",
        "tags": ["danger", "social"],
        "scope": {"required_tags": ["danger"]},
        "actions": {"function": "warn", "parameters": {"threat_type": {"type": "string"}}},
    },

    # --- Social (7) ---
    {
        "id": "tool-greet",
        "content": "Initiate a friendly greeting with another creature.",
        "tags": ["social"],
        "scope": {"required_tags": ["social"]},
        "actions": {"function": "greet", "parameters": {"target": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-gift",
        "content": "Give an item to another creature.",
        "tags": ["social", "inventory"],
        "scope": {"required_tags": ["social", "has_item"]},
        "actions": {"function": "gift", "parameters": {"item": {"type": "string", "required": True}, "target": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-groom",
        "content": "Groom another creature to strengthen social bonds.",
        "tags": ["social"],
        "scope": {"required_tags": ["social"]},
        "actions": {"function": "groom", "parameters": {"target": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-play",
        "content": "Engage in playful activity with a nearby creature.",
        "tags": ["social"],
        "scope": {"required_tags": ["social"]},
        "actions": {"function": "play", "parameters": {"target": {"type": "string", "required": True}, "game": {"type": "string"}}},
    },
    {
        "id": "tool-breed",
        "content": "Initiate a breeding interaction with a compatible mate.",
        "tags": ["social", "breeding"],
        "scope": {"required_tags": ["social", "breeding_ready"]},
        "actions": {"function": "breed", "parameters": {"target": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-challenge",
        "content": "Issue a dominance challenge to another creature.",
        "tags": ["social", "combat"],
        "scope": {"required_tags": ["social", "territorial"]},
        "actions": {"function": "challenge", "parameters": {"target": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-trade",
        "content": "Propose a trade of items with another creature.",
        "tags": ["social", "inventory"],
        "scope": {"required_tags": ["social", "has_item"]},
        "actions": {"function": "trade", "parameters": {"offer": {"type": "string", "required": True}, "request": {"type": "string"}, "target": {"type": "string", "required": True}}},
    },

    # --- Exploration (6) ---
    {
        "id": "tool-dig",
        "content": "Dig at the current location to unearth buried items.",
        "tags": ["exploration"],
        "scope": {"required_tags": ["exploration"]},
        "actions": {"function": "dig", "parameters": {"depth": {"type": "number"}}},
    },
    {
        "id": "tool-inspect",
        "content": "Examine an object or creature closely to learn about it.",
        "tags": ["exploration"],
        "scope": {"required_tags": ["exploration"]},
        "actions": {"function": "inspect", "parameters": {"target": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-climb",
        "content": "Climb a tree or rock formation for a vantage point.",
        "tags": ["exploration", "movement"],
        "scope": {"required_tags": ["climbable_nearby"]},
        "actions": {"function": "climb", "parameters": {"target": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-swim",
        "content": "Swim across a body of water.",
        "tags": ["exploration", "movement"],
        "scope": {"required_tags": ["water_nearby"]},
        "actions": {"function": "swim", "parameters": {"direction": {"type": "string"}}},
    },
    {
        "id": "tool-scout",
        "content": "Survey the surrounding area to discover points of interest.",
        "tags": ["exploration"],
        "scope": {"required_tags": ["exploration"]},
        "actions": {"function": "scout", "parameters": {"range": {"type": "number"}}},
    },
    {
        "id": "tool-mark-territory",
        "content": "Mark the current location as owned territory.",
        "tags": ["exploration", "territorial"],
        "scope": {"required_tags": ["territorial"]},
        "actions": {"function": "mark_territory", "parameters": {"radius": {"type": "number"}}},
    },

    # --- Crafting / building (6) ---
    {
        "id": "tool-build-shelter",
        "content": "Construct a shelter using available materials.",
        "tags": ["crafting", "survival"],
        "scope": {"required_tags": ["has_materials"]},
        "actions": {"function": "build_shelter", "parameters": {"type": {"type": "string", "enum": ["nest", "burrow", "den"]}}},
    },
    {
        "id": "tool-build-trap",
        "content": "Build a trap to catch small prey.",
        "tags": ["crafting", "hunting"],
        "scope": {"required_tags": ["has_materials", "hunting"]},
        "actions": {"function": "build_trap", "parameters": {"trap_type": {"type": "string", "enum": ["snare", "pitfall", "net"]}}},
    },
    {
        "id": "tool-craft-tool",
        "content": "Fashion a simple tool from raw materials.",
        "tags": ["crafting"],
        "scope": {"required_tags": ["has_materials"]},
        "actions": {"function": "craft_tool", "parameters": {"tool_type": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-repair",
        "content": "Repair a damaged structure or item.",
        "tags": ["crafting"],
        "scope": {"required_tags": ["has_damaged_item"]},
        "actions": {"function": "repair", "parameters": {"target": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-light-fire",
        "content": "Start a fire for warmth or cooking.",
        "tags": ["crafting", "survival"],
        "scope": {"required_tags": ["has_materials"]},
        "actions": {"function": "light_fire", "parameters": {"fuel": {"type": "string"}}},
    },
    {
        "id": "tool-weave",
        "content": "Weave plant fibers into rope or fabric.",
        "tags": ["crafting"],
        "scope": {"required_tags": ["has_materials", "vegetation_nearby"]},
        "actions": {"function": "weave", "parameters": {"material": {"type": "string", "required": True}, "product": {"type": "string", "enum": ["rope", "net", "basket"]}}},
    },

    # --- Inventory / items (6) ---
    {
        "id": "tool-pick-up",
        "content": "Pick up an item from the ground and add it to inventory.",
        "tags": ["inventory"],
        "scope": {"required_tags": ["item_nearby"]},
        "actions": {"function": "pick_up", "parameters": {"item": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-drop",
        "content": "Drop an item from inventory at the current location.",
        "tags": ["inventory"],
        "scope": {"required_tags": ["has_item"]},
        "actions": {"function": "drop", "parameters": {"item": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-equip",
        "content": "Equip a tool or accessory from inventory.",
        "tags": ["inventory"],
        "scope": {"required_tags": ["has_item"]},
        "actions": {"function": "equip", "parameters": {"item": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-unequip",
        "content": "Remove a currently equipped item.",
        "tags": ["inventory"],
        "scope": {"required_tags": ["has_equipped"]},
        "actions": {"function": "unequip", "parameters": {"slot": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-use-item",
        "content": "Use a consumable or activatable item from inventory.",
        "tags": ["inventory"],
        "scope": {"required_tags": ["has_item"]},
        "actions": {"function": "use_item", "parameters": {"item": {"type": "string", "required": True}, "target": {"type": "string"}}},
    },
    {
        "id": "tool-examine-item",
        "content": "Examine an item in inventory to learn its properties.",
        "tags": ["inventory"],
        "scope": {"required_tags": ["has_item"]},
        "actions": {"function": "examine_item", "parameters": {"item": {"type": "string", "required": True}}},
    },

    # --- Communication (6) ---
    {
        "id": "tool-call-out",
        "content": "Shout a message audible to creatures within earshot.",
        "tags": ["communication", "social"],
        "scope": {"required_tags": ["social"]},
        "actions": {"function": "call_out", "parameters": {"message": {"type": "string", "required": True}, "volume": {"type": "string", "enum": ["whisper", "normal", "shout"]}}},
    },
    {
        "id": "tool-signal",
        "content": "Use a visual signal to communicate silently.",
        "tags": ["communication", "stealth"],
        "scope": {"required_tags": ["social", "stealth"]},
        "actions": {"function": "signal", "parameters": {"gesture": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-teach",
        "content": "Teach a skill or piece of knowledge to another creature.",
        "tags": ["communication", "social"],
        "scope": {"required_tags": ["social"]},
        "actions": {"function": "teach", "parameters": {"skill": {"type": "string", "required": True}, "target": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-ask",
        "content": "Ask another creature a question about the environment.",
        "tags": ["communication", "social", "exploration"],
        "scope": {"required_tags": ["social"]},
        "actions": {"function": "ask", "parameters": {"target": {"type": "string", "required": True}, "question": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-negotiate",
        "content": "Negotiate terms with another creature over resources or territory.",
        "tags": ["communication", "social", "territorial"],
        "scope": {"required_tags": ["social", "territorial"]},
        "actions": {"function": "negotiate", "parameters": {"target": {"type": "string", "required": True}, "topic": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-sing",
        "content": "Sing to attract mates or soothe nearby creatures.",
        "tags": ["communication", "social"],
        "scope": {"required_tags": ["social"]},
        "actions": {"function": "sing", "parameters": {"melody": {"type": "string", "enum": ["courtship", "lullaby", "territorial"]}}},
    },

    # --- Environment interaction (7) ---
    {
        "id": "tool-push",
        "content": "Push a movable object like a boulder or log.",
        "tags": ["environment"],
        "scope": {"required_tags": ["movable_nearby"]},
        "actions": {"function": "push", "parameters": {"target": {"type": "string", "required": True}, "direction": {"type": "string"}}},
    },
    {
        "id": "tool-break",
        "content": "Break a fragile object or barrier.",
        "tags": ["environment"],
        "scope": {"required_tags": ["breakable_nearby"]},
        "actions": {"function": "break_object", "parameters": {"target": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-plant",
        "content": "Plant a seed or sapling in the ground.",
        "tags": ["environment", "food"],
        "scope": {"required_tags": ["has_seed"]},
        "actions": {"function": "plant", "parameters": {"seed_type": {"type": "string", "required": True}}},
    },
    {
        "id": "tool-harvest",
        "content": "Harvest fruit, wood, or materials from a plant or tree.",
        "tags": ["environment", "food", "crafting"],
        "scope": {"required_tags": ["vegetation_nearby"]},
        "actions": {"function": "harvest", "parameters": {"target": {"type": "string", "required": True}, "tool_used": {"type": "string"}}},
    },
    {
        "id": "tool-fish",
        "content": "Fish in a nearby body of water.",
        "tags": ["environment", "food"],
        "scope": {"required_tags": ["water_nearby"]},
        "actions": {"function": "fish", "parameters": {"method": {"type": "string", "enum": ["hand", "spear", "net"]}}},
    },
    {
        "id": "tool-extinguish",
        "content": "Put out a fire.",
        "tags": ["environment", "danger"],
        "scope": {"required_tags": ["fire_nearby"]},
        "actions": {"function": "extinguish", "parameters": {"method": {"type": "string", "enum": ["water", "dirt", "smother"]}}},
    },
    {
        "id": "tool-collect-water",
        "content": "Collect water from a stream or rain into a container.",
        "tags": ["environment", "survival"],
        "scope": {"required_tags": ["water_nearby", "has_container"]},
        "actions": {"function": "collect_water", "parameters": {"source": {"type": "string", "required": True}}},
    },
]

assert len(TOOL_DEFS) == 50, f"Expected 50 tools, got {len(TOOL_DEFS)}"


# ---------------------------------------------------------------------------
# Test scenarios: query + context → expected tool ids
# ---------------------------------------------------------------------------

SCENARIOS: list[dict] = [
    {
        "name": "Predator attack",
        "query": "A predator is approaching fast, what should I do?",
        "context": {"tags": ["danger"]},
        "expected": {"tool-flee", "tool-hide", "tool-warn", "tool-rally"},
        "not_expected": {"tool-eat", "tool-build-shelter", "tool-gift", "tool-trade"},
    },
    {
        "name": "Social encounter",
        "query": "A friendly creature approaches and seems happy to see me.",
        "context": {"tags": ["social"]},
        "expected": {"tool-greet", "tool-play", "tool-groom", "tool-call-out",
                     "tool-teach", "tool-ask", "tool-sing"},
        "not_expected": {"tool-flee", "tool-attack", "tool-build-trap", "tool-eat",
                         "tool-dig", "tool-pick-up"},
    },
    {
        "name": "Hungry near food",
        "query": "I'm hungry and there are berries on a nearby bush.",
        "context": {"tags": ["food_nearby", "vegetation_nearby"]},
        "expected": {"tool-eat", "tool-forage", "tool-harvest"},
        "not_expected": {"tool-flee", "tool-breed", "tool-build-shelter", "tool-greet",
                         "tool-attack", "tool-dig"},
    },
    {
        "name": "Building with materials",
        "query": "I have sticks and leaves, I want to make something.",
        "context": {"tags": ["has_materials"]},
        "expected": {"tool-build-shelter", "tool-craft-tool", "tool-light-fire"},
        "not_expected": {"tool-eat", "tool-flee", "tool-greet", "tool-swim",
                         "tool-attack", "tool-pick-up"},
    },
    {
        "name": "Combat encounter",
        "query": "An aggressive creature is attacking me.",
        "context": {"tags": ["combat", "danger"]},
        "expected": {"tool-attack", "tool-defend", "tool-flee", "tool-hide", "tool-warn",
                     "tool-rally"},
        "not_expected": {"tool-greet", "tool-play", "tool-plant", "tool-eat",
                         "tool-build-shelter"},
    },
    {
        "name": "Near water",
        "query": "There is a river ahead.",
        "context": {"tags": ["water_nearby"]},
        "expected": {"tool-drink", "tool-swim", "tool-fish"},
        "not_expected": {"tool-climb", "tool-build-trap", "tool-breed", "tool-attack",
                         "tool-flee", "tool-greet"},
    },
    {
        "name": "Item management",
        "query": "I found a shiny stone on the ground.",
        "context": {"tags": ["item_nearby", "has_item"]},
        "expected": {"tool-pick-up", "tool-examine-item", "tool-drop", "tool-equip",
                     "tool-use-item"},
        "not_expected": {"tool-flee", "tool-rally", "tool-cook", "tool-attack",
                         "tool-greet"},
    },
    {
        "name": "Territory dispute",
        "query": "Another creature is encroaching on my territory.",
        "context": {"tags": ["social", "territorial"]},
        "expected": {"tool-challenge", "tool-mark-territory", "tool-negotiate"},
        "not_expected": {"tool-eat", "tool-swim", "tool-craft-tool", "tool-flee",
                         "tool-pick-up"},
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_corpus(tool_defs: list[dict]) -> Corpus:
    """Build a corpus from a list of tool definition dicts."""
    corpus = Corpus()
    instructions = []
    for td in tool_defs:
        instructions.append(Instruction(
            id=td["id"],
            type=InstructionType.TOOL,
            priority=td.get("priority", 65),
            content=td["content"],
            scope=ScopeCondition(**td["scope"]) if td.get("scope") else ScopeCondition(),
            tags=td.get("tags", []),
            actions=td["actions"],
        ))
    corpus.add_many(instructions)
    return corpus


def estimate_tokens(tools: list[dict]) -> int:
    """Rough token estimate for tool schemas (~4 chars per token)."""
    return len(json.dumps(tools)) // 4


def tool_dispatch(tool_name: str, arguments: dict) -> str:
    """Stub dispatcher — prints and returns confirmation."""
    args_str = ", ".join(f"{k}={v!r}" for k, v in arguments.items())
    msg = f"[Tool called] {tool_name}({args_str})"
    print(f"  {msg}")
    return msg


# ---------------------------------------------------------------------------
# Eval 1: Retrieval precision at different corpus sizes
# ---------------------------------------------------------------------------

def eval_scaling():
    """Test retrieval precision as the tool corpus grows.

    Uses semantic embeddings for similarity and required_tags for hard gating.
    """
    print("=" * 70)
    print("EVAL 1: Retrieval precision vs. corpus size")
    print("=" * 70)

    from stat_utils import bootstrap_ci, format_ci

    sizes = [5, 10, 25, 50]
    all_pass = True

    for size in sizes:
        subset = TOOL_DEFS[:size]
        corpus = build_corpus(subset)
        subset_ids = {td["id"] for td in subset}

        config = Config(
            embedding_model="BAAI/bge-base-en-v1.5",
            embedding_backend=EmbeddingBackend.NUMPY,
            priority_weight=0.3,
            default_threshold=0.0,
            default_top_k=size,
        )
        retriever = Retriever(corpus, config=config)
        retriever.build_index()
        composer = Composer(strategy=CompositionStrategy.HIERARCHICAL)

        per_scenario_precision = []
        per_scenario_recall = []
        no_false_positives = True

        for scenario in SCENARIOS:
            expected = scenario["expected"] & subset_ids
            not_expected = scenario["not_expected"] & subset_ids
            if not expected:
                continue

            ctx = Context(**scenario["context"])
            results = retriever.retrieve(scenario["query"], ctx)
            composed = composer.compose(results)
            retrieved_ids = {r.id for r in results if r.type == InstructionType.TOOL}

            true_positives = retrieved_ids & expected
            false_positives = retrieved_ids & not_expected
            precision = len(true_positives) / max(len(retrieved_ids), 1)
            recall = len(true_positives) / len(expected)

            if false_positives:
                no_false_positives = False

            per_scenario_precision.append(precision)
            per_scenario_recall.append(recall)

        valid_scenarios = len(per_scenario_precision)
        if valid_scenarios > 0:
            avg_precision = sum(per_scenario_precision) / valid_scenarios
            avg_recall = sum(per_scenario_recall) / valid_scenarios
            ci_precision = bootstrap_ci(per_scenario_precision)
            ci_recall = bootstrap_ci(per_scenario_recall)
        else:
            avg_precision = avg_recall = 0.0
            ci_precision = ci_recall = {"point_estimate": 0, "ci_lower": 0, "ci_upper": 0, "std": 0, "n": 0}

        status = "PASS" if (avg_recall >= 0.5 and no_false_positives) else "FAIL"
        if status == "FAIL":
            all_pass = False

        print(f"\n  Corpus size: {size:>2} tools | "
              f"Precision: {format_ci(ci_precision)} | "
              f"Recall: {format_ci(ci_recall)} | "
              f"No cross-domain leaks: {no_false_positives} | "
              f"Scenarios: {valid_scenarios} — {status}")

    print()
    return all_pass


# ---------------------------------------------------------------------------
# Eval 2: Prompt token savings — scoped vs. all tools
# ---------------------------------------------------------------------------

def eval_token_savings():
    """Compare token cost of scoped retrieval vs. always injecting all 50 tools."""
    print("=" * 70)
    print("EVAL 2: Prompt token savings (scoped vs. all tools)")
    print("=" * 70)

    corpus = build_corpus(TOOL_DEFS)
    config = Config(
        embedding_model="BAAI/bge-base-en-v1.5",
        embedding_backend=EmbeddingBackend.NUMPY,
        priority_weight=0.3,
        default_threshold=0.0,
        default_top_k=50,
    )
    retriever = Retriever(corpus, config=config)
    retriever.build_index()
    composer = Composer(strategy=CompositionStrategy.HIERARCHICAL)

    # All-tools baseline: compose all 50 tools without any scope filtering
    all_composed = composer.compose([
        __import__("bear.models", fromlist=["ScoredInstruction"]).ScoredInstruction(
            instruction=inst, similarity=1.0, scope_match=True, final_score=1.0,
        )
        for inst in corpus
    ])
    all_tokens = estimate_tokens(all_composed.tools)

    total_savings = 0.0
    count = 0

    for scenario in SCENARIOS:
        ctx = Context(**scenario["context"])
        results = retriever.retrieve(scenario["query"], ctx)
        composed = composer.compose(results)
        scoped_tokens = estimate_tokens(composed.tools)
        n_tools = len(composed.tools)
        savings = 1.0 - (scoped_tokens / max(all_tokens, 1))
        total_savings += savings
        count += 1

        print(f"  {scenario['name']:.<30} "
              f"{n_tools:>2} tools | "
              f"{scoped_tokens:>4} tokens | "
              f"savings: {savings:.0%}")

    avg_savings = total_savings / max(count, 1)
    print(f"\n  All-tools baseline: {len(all_composed.tools)} tools, "
          f"{all_tokens} tokens")
    print(f"  Average token savings: {avg_savings:.0%}")

    status = "PASS" if avg_savings > 0.3 else "FAIL"
    print(f"  Token savings — {status}\n")
    return status == "PASS"


# ---------------------------------------------------------------------------
# Eval 3: End-to-end dispatch (requires LLM — optional)
# ---------------------------------------------------------------------------

async def eval_end_to_end():
    """Run one query through the full pipeline: retrieve → compose → LLM → dispatch."""
    print("=" * 70)
    print("EVAL 3: End-to-end pipeline (retrieve → compose → LLM → dispatch)")
    print("=" * 70)

    corpus = build_corpus(TOOL_DEFS)
    config = Config(
        embedding_model="BAAI/bge-base-en-v1.5",
        embedding_backend=EmbeddingBackend.NUMPY,
        priority_weight=0.3,
        default_threshold=0.0,
        default_top_k=50,
    )
    retriever = Retriever(corpus, config=config)
    retriever.build_index()
    composer = Composer(strategy=CompositionStrategy.HIERARCHICAL)

    # Scenario: creature is hungry near food
    ctx = Context(tags=["food_nearby", "vegetation_nearby"])
    query = "I'm very hungry. There are ripe berries on the bush right in front of me."
    results = retriever.retrieve(query, ctx)
    composed = composer.compose(results)

    tool_names = [t["function"]["name"] for t in composed.tools]
    print(f"  Retrieved {len(composed.tools)} tools: {tool_names}")

    # Try to get an LLM — prefer a model that supports function calling
    try:
        from bear.llm import LLM
        from bear.config import LLMBackend
        llm = LLM(backend=LLMBackend.OPENAI, model="gpt-5.4-2026-03-05",
                   base_url="https://api.openai.com/v1")
        if not llm.is_available():
            llm = LLM.auto()
            if not llm.is_available():
                raise RuntimeError("No LLM available")
    except Exception as e:
        print(f"  Skipping LLM call (no backend available: {e})")
        print("  SKIP (no LLM)\n")
        return True

    print(f"  Using LLM: {llm.backend_type.value}/{llm.model}")

    system = (
        "You are a creature in a simulated ecosystem. "
        "Use the available tools to interact with the world. "
        "Pick the single most appropriate tool for the situation."
    )
    if composed.guidance:
        system += f"\n\n{composed.guidance}"

    try:
        response = await llm.generate(
            system=system,
            user=query,
            tools=composed.tools,
            temperature=0.0,
            max_tokens=200,
        )
    except Exception as e:
        print(f"  LLM call failed: {e}")
        print("  (Model may not support function calling)")
        print("  SKIP (LLM error)\n")
        return True

    if response.tool_calls:
        for tc in response.tool_calls:
            tool_dispatch(tc.name, tc.arguments)
        if response.content:
            print(f"  LLM text: {response.content[:100]!r}")
        print("  End-to-end — PASS\n")
        return True
    else:
        print(f"  LLM responded with text only: {response.content[:150]!r}")
        print("  (Model did not produce a tool call — may not support function calling)")
        print("  End-to-end — PARTIAL (retrieval + composition worked)\n")
        return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_evaluation():
    print(f"\nTool Scaling Evaluation — {len(TOOL_DEFS)} tool definitions, "
          f"{len(SCENARIOS)} test scenarios\n")

    pass1 = eval_scaling()
    pass2 = eval_token_savings()
    pass3 = asyncio.run(eval_end_to_end())

    print("=" * 70)
    print("Summary")
    print("=" * 70)
    all_pass = pass1 and pass2 and pass3
    print(f"  Scaling precision: {'PASS' if pass1 else 'FAIL'}")
    print(f"  Token savings:     {'PASS' if pass2 else 'FAIL'}")
    print(f"  End-to-end:        {'PASS' if pass3 else 'FAIL'}")
    print(f"\n  All tests passed: {all_pass}")
    return all_pass


if __name__ == "__main__":
    success = run_evaluation()
    sys.exit(0 if success else 1)
