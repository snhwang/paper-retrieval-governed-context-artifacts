"""Evaluate BEAR retrieval quality: Precision@K, Recall@K, F1@K across configurations.

Usage:
    python eval_retrieval.py              # hash embeddings (fast, deterministic)
    python eval_retrieval.py --semantic   # sentence-transformers (slower, meaningful)
"""

import argparse
import sys
from pathlib import Path

import numpy as np

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from bear import Corpus, Config, Context, Retriever, EmbeddingBackend
from stat_utils import bootstrap_ci, format_ci, format_ci_latex

EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"

# ---------------------------------------------------------------------------
# Ground-truth test queries for Pet Sim
# Each entry: (query_text, context_tags, expected_instruction_ids)
# Expected IDs are derived from scope conditions in the YAML files.
# ---------------------------------------------------------------------------

TEST_QUERIES = [
    # Dog stimulus responses
    (
        "A ball has appeared near the dog",
        ["dog", "ball_present", "stimulus_present"],
        {"dog-personality", "dog-sees-ball", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "A treat has appeared near the dog",
        ["dog", "treat_present", "stimulus_present"],
        {"dog-personality", "dog-sees-treat", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The dog has reached the ball",
        ["dog", "at_ball"],
        {"dog-personality", "dog-reaches-ball", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The dog has reached the treat",
        ["dog", "at_treat"],
        {"dog-personality", "dog-reaches-treat", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The dog is idle with nothing to do",
        ["dog", "idle"],
        {"dog-personality", "dog-idle-wander", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The dog is feeling very unhappy",
        ["dog", "unhappy"],
        {"dog-personality", "dog-unhappy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The dog is feeling very happy and joyful",
        ["dog", "very_happy"],
        {"dog-personality", "dog-very-happy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    # Cat stimulus responses
    (
        "A treat has appeared near the cat",
        ["cat", "treat_present", "stimulus_present"],
        {"cat-personality", "cat-sees-treat", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "A ball has appeared near the cat",
        ["cat", "ball_present", "stimulus_present"],
        {"cat-personality", "cat-sees-ball", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The cat has reached the treat",
        ["cat", "at_treat"],
        {"cat-personality", "cat-reaches-treat", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The cat is idle and looking around",
        ["cat", "idle"],
        {"cat-personality", "cat-idle-perch", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The cat is sitting on an elevated perch",
        ["cat", "on_perch"],
        {"cat-personality", "cat-on-perch", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    # Player interaction: dog petting at different relationship tiers
    (
        "A bonded player is petting the dog",
        ["dog", "being_petted", "player_bonded"],
        {"dog-personality", "dog-petted-bonded", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "A friendly player is petting the dog",
        ["dog", "being_petted", "player_friend"],
        {"dog-personality", "dog-petted-friend", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "A neutral player is petting the dog",
        ["dog", "being_petted", "player_neutral"],
        {"dog-personality", "dog-petted-neutral", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "A wary player is petting the dog",
        ["dog", "being_petted", "player_wary"],
        {"dog-personality", "dog-petted-wary", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    # Player interaction: cat petting at different relationship tiers
    (
        "A bonded player is petting the cat",
        ["cat", "being_petted", "player_bonded"],
        {"cat-personality", "cat-petted-bonded", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "A wary player is petting the cat",
        ["cat", "being_petted", "player_wary"],
        {"cat-personality", "cat-petted-wary", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    # Inter-pet interactions
    (
        "The dog approaches the cat playfully",
        ["dog", "cat_nearby", "mood_playful"],
        {"dog-personality", "dog-approaches-cat-playful", "mood-playful-active", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The cat is annoyed by the nearby dog",
        ["cat", "dog_nearby", "mood_annoyed"],
        {"cat-personality", "cat-annoyed-by-dog", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    # cat-annoyed-by-dog (priority 60) conflicts_with cat-tolerates-dog (priority 55),
    # so conflict resolution removes cat-tolerates-dog even though its required_tags match.
    (
        "The cat tolerates the nearby dog contentedly",
        ["cat", "dog_nearby", "mood_content"],
        {"cat-personality", "cat-annoyed-by-dog", "mood-content-peaceful", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    # Mood-specific queries (soft scope — no required_tags on mood instructions)
    (
        "The dog is in an excited mood",
        ["dog", "mood_excited"],
        {"dog-personality", "mood-excited-energy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The cat is feeling sleepy",
        ["cat", "mood_sleepy"],
        {"cat-personality", "mood-sleepy-slow", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The dog is cautious and alert",
        ["dog", "mood_cautious"],
        {"dog-personality", "mood-cautious-alert", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The cat is in a playful mood chasing things",
        ["cat", "mood_playful"],
        {"cat-personality", "mood-playful-active", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The dog seems content and relaxed",
        ["dog", "mood_content"],
        {"dog-personality", "mood-content-peaceful", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The cat is excited and energetic",
        ["cat", "mood_excited"],
        {"cat-personality", "mood-excited-energy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The dog is drowsy and falling asleep",
        ["dog", "mood_sleepy"],
        {"dog-personality", "mood-sleepy-slow", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The cat is cautious and watching carefully",
        ["cat", "mood_cautious"],
        {"cat-personality", "mood-cautious-alert", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The dog is playful and bouncing around",
        ["dog", "mood_playful"],
        {"dog-personality", "mood-playful-active", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The cat seems content and peaceful",
        ["cat", "mood_content"],
        {"cat-personality", "mood-content-peaceful", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    # Cross-context: dog with ball + mood
    (
        "An excited dog sees a ball",
        ["dog", "ball_present", "mood_excited", "stimulus_present"],
        {"dog-personality", "dog-sees-ball", "mood-excited-energy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    # Cross-context: cat petting + mood
    (
        "A bonded player pets the sleepy cat",
        ["cat", "being_petted", "player_bonded", "mood_sleepy"],
        {"cat-personality", "cat-petted-bonded", "mood-sleepy-slow", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    # dog-approaches-cat-playful (priority 55) conflicts_with dog-approaches-cat-cautious (priority 50),
    # so conflict resolution removes dog-approaches-cat-cautious even though its required_tags match.
    (
        "The dog cautiously approaches the cat",
        ["dog", "cat_nearby"],
        {"dog-personality", "dog-approaches-cat-playful", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    # Cat curious about dog
    (
        "The cat is curious about the nearby dog",
        ["cat", "dog_nearby"],
        {"cat-personality", "cat-curious-about-dog", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    # Cat unhappy
    (
        "The cat is feeling unhappy and restless",
        ["cat", "unhappy"],
        {"cat-personality", "cat-unhappy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    # Cat very happy
    (
        "The cat is very happy and content",
        ["cat", "very_happy"],
        {"cat-personality", "cat-very-happy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    # --- Verbal commands (dog) ---
    (
        "The player tells the dog to come",
        ["dog", "verbal_command"],
        {"dog-personality", "dog-command-come", "dog-command-general", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The player tells the dog to sit",
        ["dog", "verbal_command"],
        {"dog-personality", "dog-command-sit", "dog-command-general", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The player tells the dog to stay",
        ["dog", "verbal_command"],
        {"dog-personality", "dog-command-stay", "dog-command-general", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The player tells the dog to fetch",
        ["dog", "verbal_command"],
        {"dog-personality", "dog-command-fetch", "dog-command-general", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The player tells the dog to shake paw",
        ["dog", "verbal_command"],
        {"dog-personality", "dog-command-shake", "dog-command-general", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The player tells the dog to speak",
        ["dog", "verbal_command"],
        {"dog-personality", "dog-command-speak", "dog-command-general", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The player tells the dog to spin",
        ["dog", "verbal_command"],
        {"dog-personality", "dog-command-spin", "dog-command-general", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    # --- Verbal commands (cat) ---
    (
        "The player tells the cat to come",
        ["cat", "verbal_command"],
        {"cat-personality", "cat-command-come", "cat-command-general", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The player tells the cat to sit",
        ["cat", "verbal_command"],
        {"cat-personality", "cat-command-sit", "cat-command-general", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The player tells the cat to stay",
        ["cat", "verbal_command"],
        {"cat-personality", "cat-command-stay", "cat-command-general", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    # --- Ball lifecycle ---
    (
        "A ball is sitting fresh on the ground",
        ["ball"],
        {"ball-idle-fresh", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The ball has been sitting for a while and is aging",
        ["ball", "aging"],
        {"ball-aging", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "A pet is approaching the ball",
        ["ball", "pet_nearby"],
        {"ball-pet-approaching", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "A pet has reached the ball",
        ["ball", "pet_arrived"],
        {"ball-pet-arrived", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    # --- Treat lifecycle ---
    (
        "A treat is sitting fresh on the ground",
        ["treat"],
        {"treat-idle-fresh", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "The treat has been sitting for a while and is aging",
        ["treat", "aging"],
        {"treat-aging", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "A pet is approaching the treat",
        ["treat", "pet_nearby"],
        {"treat-pet-approaching", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "A pet has reached the treat",
        ["treat", "pet_arrived"],
        {"treat-pet-arrived", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    # --- Additional cat petting tiers ---
    (
        "A friendly player is petting the cat",
        ["cat", "being_petted", "player_friend"],
        {"cat-personality", "cat-petted-friend", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    (
        "A neutral player is petting the cat",
        ["cat", "being_petted", "player_neutral"],
        {"cat-personality", "cat-petted-neutral", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    # --- Cat reaches ball ---
    (
        "The cat has reached the ball",
        ["cat", "at_ball"],
        {"cat-personality", "cat-reaches-ball", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    # --- Cat tolerates dog (explicit mood_content) ---
    (
        "The cat is content with the nearby dog",
        ["cat", "dog_nearby", "mood_content"],
        {"cat-personality", "cat-tolerates-dog", "mood-content-peaceful", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
    # --- Dog approaches cat cautiously (no playful mood) ---
    (
        "The dog sees the cat and approaches carefully",
        ["dog", "cat_nearby"],
        {"dog-personality", "dog-approaches-cat-playful", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"},
    ),
]

# ---------------------------------------------------------------------------
# Relaxed expected sets: includes semantically plausible retrievals beyond
# strict tag-determined ground truth.  Used to compute a second precision
# score that does not penalise useful semantic discovery.
#
# Rules applied:
#   - Mood instructions consonant with the scenario are acceptable
#     (e.g. mood-excited-energy when a ball appears).
#   - Mood instructions dissonant with the scenario are NOT acceptable
#     (e.g. mood-excited-energy when the pet is unhappy/sleepy).
#   - Other petting tiers for the same pet are acceptable (they share
#     required_tags and provide contextually relevant contrast).
#   - Inter-pet instructions for closely related scenarios are acceptable
#     (e.g. cat-curious-about-dog when cat tolerates dog).
# ---------------------------------------------------------------------------

RELAXED_EXTRAS: dict[str, set[str]] = {
    # Stimulus responses — excitement/playfulness is natural
    "A ball has appeared near the dog": {"mood-excited-energy", "mood-playful-active"},
    "A treat has appeared near the dog": {"mood-excited-energy"},
    "A ball has appeared near the cat": {"mood-playful-active", "mood-cautious-alert"},
    "A treat has appeared near the cat": {"mood-excited-energy", "mood-cautious-alert"},
    "The dog has reached the ball": {"mood-excited-energy", "mood-playful-active"},
    "The dog has reached the treat": {"mood-excited-energy", "mood-content-peaceful"},
    "The cat has reached the treat": {"mood-content-peaceful"},
    # Idle — sleepy/content are plausible idle moods
    "The dog is idle with nothing to do": {"mood-sleepy-slow", "mood-content-peaceful"},
    "The cat is idle and looking around": {"mood-cautious-alert", "mood-content-peaceful"},
    "The cat is sitting on an elevated perch": set(),
    # Emotional states — only consonant moods
    "The dog is feeling very unhappy": set(),  # no mood is appropriate
    "The dog is feeling very happy and joyful": {"mood-excited-energy", "mood-content-peaceful", "mood-playful-active"},
    "The cat is feeling unhappy and restless": set(),
    "The cat is very happy and content": {"mood-content-peaceful", "mood-playful-active"},
    # Petting — other tiers for same pet are contextually relevant
    "A bonded player is petting the dog": {"dog-petted-friend", "dog-petted-neutral", "dog-petted-wary", "mood-excited-energy", "mood-playful-active"},
    "A friendly player is petting the dog": {"dog-petted-bonded", "dog-petted-neutral", "dog-petted-wary", "mood-playful-active", "mood-excited-energy"},
    "A neutral player is petting the dog": {"dog-petted-bonded", "dog-petted-friend", "dog-petted-wary"},
    "A wary player is petting the dog": {"dog-petted-bonded", "dog-petted-friend", "dog-petted-neutral", "mood-cautious-alert"},
    "A bonded player is petting the cat": {"cat-petted-friend", "cat-petted-neutral", "cat-petted-wary"},
    "A wary player is petting the cat": {"cat-petted-bonded", "cat-petted-friend", "cat-petted-neutral", "mood-cautious-alert"},
    # Inter-pet interactions
    "The dog approaches the cat playfully": {"mood-excited-energy"},
    "The cat is annoyed by the nearby dog": {"cat-curious-about-dog", "mood-cautious-alert"},
    "The cat tolerates the nearby dog contentedly": {"cat-curious-about-dog"},
    "The dog cautiously approaches the cat": {"mood-cautious-alert"},  # dog-approaches-cat-playful now in strict expected
    "The cat is curious about the nearby dog": {"cat-annoyed-by-dog", "mood-cautious-alert"},
    # Mood queries — only the queried mood is expected
    "The dog is in an excited mood": set(),
    "The cat is feeling sleepy": set(),
    "The dog is cautious and alert": set(),
    "The cat is in a playful mood chasing things": set(),
    "The dog seems content and relaxed": set(),
    "The cat is excited and energetic": set(),
    "The dog is drowsy and falling asleep": set(),
    "The cat is cautious and watching carefully": set(),
    "The dog is playful and bouncing around": set(),
    "The cat seems content and peaceful": set(),
    # Cross-context
    "An excited dog sees a ball": {"mood-playful-active"},
    "A bonded player pets the sleepy cat": {"cat-petted-friend", "cat-petted-neutral", "cat-petted-wary"},
    # Verbal commands — other commands for the same pet are plausible extras
    "The player tells the dog to come": {"dog-command-fetch", "dog-command-sit", "dog-command-stay", "dog-command-shake", "dog-command-speak", "dog-command-spin"},
    "The player tells the dog to sit": {"dog-command-come", "dog-command-stay", "dog-command-fetch", "dog-command-shake", "dog-command-speak", "dog-command-spin"},
    "The player tells the dog to stay": {"dog-command-come", "dog-command-sit", "dog-command-fetch", "dog-command-shake", "dog-command-speak", "dog-command-spin"},
    "The player tells the dog to fetch": {"dog-command-come", "dog-command-sit", "dog-command-stay", "dog-command-shake", "dog-command-speak", "dog-command-spin"},
    "The player tells the dog to shake paw": {"dog-command-come", "dog-command-sit", "dog-command-stay", "dog-command-fetch", "dog-command-speak", "dog-command-spin"},
    "The player tells the dog to speak": {"dog-command-come", "dog-command-sit", "dog-command-stay", "dog-command-fetch", "dog-command-shake", "dog-command-spin"},
    "The player tells the dog to spin": {"dog-command-come", "dog-command-sit", "dog-command-stay", "dog-command-fetch", "dog-command-shake", "dog-command-speak"},
    "The player tells the cat to come": {"cat-command-sit", "cat-command-stay"},
    "The player tells the cat to sit": {"cat-command-come", "cat-command-stay"},
    "The player tells the cat to stay": {"cat-command-come", "cat-command-sit"},
    # Ball/treat lifecycle — object instructions are plausible extras
    "A ball is sitting fresh on the ground": {"ball-aging"},
    "The ball has been sitting for a while and is aging": {"ball-idle-fresh"},
    "A pet is approaching the ball": {"ball-idle-fresh"},
    "A pet has reached the ball": {"ball-pet-approaching"},
    "A treat is sitting fresh on the ground": {"treat-aging"},
    "The treat has been sitting for a while and is aging": {"treat-idle-fresh"},
    "A pet is approaching the treat": {"treat-idle-fresh"},
    "A pet has reached the treat": {"treat-pet-approaching"},
    # Additional cat interactions
    "A friendly player is petting the cat": {"cat-petted-bonded", "cat-petted-neutral", "cat-petted-wary"},
    "A neutral player is petting the cat": {"cat-petted-bonded", "cat-petted-friend", "cat-petted-wary"},
    "The cat has reached the ball": {"mood-playful-active"},
    "The cat is content with the nearby dog": {"cat-curious-about-dog", "cat-annoyed-by-dog"},
    "The dog sees the cat and approaches carefully": {"mood-cautious-alert", "dog-approaches-cat-cautious"},
}


def compute_metrics(retrieved_ids: set[str], expected_ids: set[str], k: int):
    """Compute Precision@K, Recall@K, F1@K."""
    retrieved_at_k = retrieved_ids  # Already truncated to k by retriever
    true_positives = len(retrieved_at_k & expected_ids)
    precision = true_positives / len(retrieved_at_k) if retrieved_at_k else 0.0
    recall = true_positives / len(expected_ids) if expected_ids else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def run_evaluation(use_semantic: bool = False):
    model = EMBEDDING_MODEL if use_semantic else "hash"
    print(f"Embedding model: {model}\n")

    # Load Pet Sim corpus
    instructions_dir = project_root / "pet_sim" / "instructions"
    if not instructions_dir.exists():
        print(f"ERROR: Instructions directory not found: {instructions_dir}")
        sys.exit(1)

    corpus = Corpus.from_directory(str(instructions_dir))
    print(f"Loaded corpus with {len(corpus)} instructions\n")

    # Configuration 1: Full BEAR pipeline
    config_full = Config(
        embedding_model=model,
        embedding_backend=EmbeddingBackend.NUMPY,
        priority_weight=0.3,
        default_threshold=0.3,
        default_top_k=10,
        mandatory_tags=["safety"],
    )

    # Configuration 2: Pure similarity (no priority, no mandatory, empty context)
    config_similarity = Config(
        embedding_model=model,
        embedding_backend=EmbeddingBackend.NUMPY,
        priority_weight=0.0,
        default_threshold=0.3,
        default_top_k=10,
        mandatory_tags=[],
    )

    # Configuration 3: High priority weight (scope + priority dominant)
    config_priority = Config(
        embedding_model=model,
        embedding_backend=EmbeddingBackend.NUMPY,
        priority_weight=0.7,
        default_threshold=0.3,
        default_top_k=10,
        mandatory_tags=["safety"],
    )

    configs = {
        "Full BEAR ($\\alpha=0.3$)": (config_full, True),
        "Pure Similarity ($\\alpha=0$)": (config_similarity, False),
        "Priority-Heavy ($\\alpha=0.7$)": (config_priority, True),
    }

    results = {}

    for name, (config, use_context) in configs.items():
        retriever = Retriever(corpus, config=config)
        retriever.build_index()

        all_precision, all_recall, all_f1 = [], [], []
        all_rp, all_rr, all_rf1 = [], [], []  # relaxed

        for query_text, context_tags, expected_ids in TEST_QUERIES:
            if use_context:
                context = Context(tags=context_tags)
            else:
                context = Context()

            retrieved = retriever.retrieve(query_text, context, top_k=10)
            retrieved_ids = {r.id for r in retrieved}

            # Strict metrics (tag-determined ground truth)
            p, r, f = compute_metrics(retrieved_ids, expected_ids, k=10)
            all_precision.append(p)
            all_recall.append(r)
            all_f1.append(f)

            # Relaxed metrics (includes semantically plausible extras)
            relaxed_ids = expected_ids | RELAXED_EXTRAS.get(query_text, set())
            rp, rr, rf = compute_metrics(retrieved_ids, relaxed_ids, k=10)
            all_rp.append(rp)
            all_rr.append(rr)
            all_rf1.append(rf)

        avg_p = sum(all_precision) / len(all_precision)
        avg_r = sum(all_recall) / len(all_recall)
        avg_f1 = sum(all_f1) / len(all_f1)
        avg_rp = sum(all_rp) / len(all_rp)
        avg_rr = sum(all_rr) / len(all_rr)
        avg_rf1 = sum(all_rf1) / len(all_rf1)

        # Bootstrap 95% CIs over queries
        ci_f1 = bootstrap_ci(all_f1)
        ci_rf1 = bootstrap_ci(all_rf1)
        ci_p = bootstrap_ci(all_precision)
        ci_r = bootstrap_ci(all_recall)
        ci_rp = bootstrap_ci(all_rp)
        ci_rr = bootstrap_ci(all_rr)

        results[name] = {
            "strict": {"p": avg_p, "r": avg_r, "f1": avg_f1,
                        "ci_p": ci_p, "ci_r": ci_r, "ci_f1": ci_f1},
            "relaxed": {"p": avg_rp, "r": avg_rr, "f1": avg_rf1,
                         "ci_p": ci_rp, "ci_r": ci_rr, "ci_f1": ci_rf1},
        }

        print(f"{name}:")
        print(f"  Strict:  P@10={format_ci(ci_p)}, R@10={format_ci(ci_r)}, F1@10={format_ci(ci_f1)}")
        print(f"  Relaxed: P@10={format_ci(ci_rp)}, R@10={format_ci(ci_rr)}, F1@10={format_ci(ci_rf1)}")
        print()

    # Output LaTeX table (dual metrics with CIs)
    print("\n% === LaTeX Table ===")
    print("\\begin{table}[t]")
    print("\\caption{Retrieval quality on Pet Sim corpus "
          f"({len(TEST_QUERIES)} queries, $k=10$, BAAI/bge-base-en-v1.5).")
    print("Values show mean with 95\\% bootstrap CI (10,000 iterations).}")
    print("\\label{tab:retrieval}")
    print("\\begin{tabular}{@{}lcc@{}}")
    print("\\toprule")
    print("Configuration & Strict F1 & Relaxed F1 \\\\")
    print("\\midrule")
    for name, data in results.items():
        sf1 = format_ci_latex(data["strict"]["ci_f1"])
        rf1 = format_ci_latex(data["relaxed"]["ci_f1"])
        print(f"{name} & ${sf1}$ & ${rf1}$ \\\\")
    print("\\bottomrule")
    print("\\end{tabular}")
    print("\\end{table}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--semantic", action="store_true",
                        help="Use sentence-transformers instead of hash embeddings")
    args = parser.parse_args()
    run_evaluation(use_semantic=args.semantic)
