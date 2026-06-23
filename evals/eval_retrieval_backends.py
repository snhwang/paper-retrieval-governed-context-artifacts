"""Compare retrieval backends: Dense (BGE, Qwen3) vs. Sparse (BM25) vs. Hybrid (ITR).

Runs the same retrieval evaluation (Pet Simulation corpus, 37 ground-truth
queries) across multiple retrieval backends and embedding models:

  1. BEAR + BAAI/bge-base-en-v1.5  (768-dim dense, current default)
  2. BEAR + Qwen/Qwen3-Embedding-0.6B  (1024-dim dense, SOTA-class)
  3. BEAR + BAAI/bge-m3  (1024-dim dense, multilingual)
  5. BEAR + BM25  (sparse lexical retrieval, no embeddings)
  6. BEAR + ITR  (hybrid dense+BM25 fusion via ITR, with BEAR governance)

All configurations use the same scope-gated retrieval pipeline (required_tags,
mandatory injection, conflict resolution) — only the matching backend differs.
This isolates the contribution of the retrieval signal (dense vs. sparse vs.
hybrid) from the governance mechanisms.

Usage:
    python eval_retrieval_backends.py                          # BGE + BM25 (no Qwen3)
    python eval_retrieval_backends.py --all                    # all backends
    python eval_retrieval_backends.py --models bge bge-m3      # BGE variants
    python eval_retrieval_backends.py --models bm25            # BM25 only
    python eval_retrieval_backends.py --models itr             # ITR hybrid only
"""

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import torch

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bear import Corpus, Config, Context, Retriever, EmbeddingBackend  # noqa: E402

# ---------------------------------------------------------------------------
# Platform / accelerator detection
# ---------------------------------------------------------------------------

_IS_MAC = platform.system() == "Darwin"
_HAS_CUDA = torch.cuda.is_available()
_HAS_FLASH_ATTN = False
try:
    import flash_attn  # noqa: F401
    _HAS_FLASH_ATTN = True
except ImportError:
    pass



def _qwen3_device() -> str | None:
    """Qwen3 GQA heads crash MPS on Apple Silicon; force CPU there."""
    if _IS_MAC:
        return "cpu"
    return None  # auto-detect (CUDA if available)

# Re-use ground truth from eval_retrieval
from eval_retrieval import (  # noqa: E402
    TEST_QUERIES,
    RELAXED_EXTRAS,
    compute_metrics,
)

# ---------------------------------------------------------------------------
# Model / backend configurations
# ---------------------------------------------------------------------------

BACKEND_CONFIGS = {
    "bge": {
        "label": "BEAR + BGE-base v1.5",
        "short": "BGE-base",
        "embedding_model": "BAAI/bge-base-en-v1.5",
        "embedding_backend": EmbeddingBackend.NUMPY,
        "embedding_dim": 768,
        "embedding_query_prefix": "Represent this sentence for retrieving relevant documents: ",
        "embedding_passage_prefix": "",
    },
    "qwen3": {
        "label": "BEAR + Qwen3-Embedding-0.6B",
        "short": "Qwen3-0.6B",
        "embedding_model": "Qwen/Qwen3-Embedding-0.6B",
        "embedding_backend": EmbeddingBackend.NUMPY,
        "embedding_dim": 1024,
        "embedding_query_prefix": "Instruct: Retrieve behavioral instructions relevant to this query\nQuery: ",
        "embedding_passage_prefix": "",
        "embedding_device": _qwen3_device(),
    },
    "qwen3-4b": {
        "label": "BEAR + Qwen3-Embedding-4B",
        "short": "Qwen3-4B",
        "embedding_model": "Qwen/Qwen3-Embedding-4B",
        "embedding_backend": EmbeddingBackend.NUMPY,
        "embedding_dim": 2560,
        "embedding_query_prefix": "Instruct: Retrieve behavioral instructions relevant to this query\nQuery: ",
        "embedding_passage_prefix": "",
        "embedding_device": _qwen3_device(),
    },
    "bge-m3-mlx": {
        "label": "BEAR + BGE-M3 (MLX fp16)",
        "short": "BGE-M3 MLX",
        "embedding_model": "mlx-community/bge-m3-mlx-fp16",
        "embedding_backend": EmbeddingBackend.NUMPY,
        "embedding_dim": 1024,
        "embedding_query_prefix": "Represent this sentence for retrieving relevant documents: ",
        "embedding_passage_prefix": "",
    },
    "qwen3-mlx": {
        "label": "BEAR + Qwen3-0.6B (MLX 8bit)",
        "short": "Qwen3-0.6B MLX",
        "embedding_model": "mlx-community/Qwen3-Embedding-0.6B-8bit",
        "embedding_backend": EmbeddingBackend.NUMPY,
        "embedding_dim": 1024,
        "embedding_query_prefix": "Instruct: Retrieve behavioral instructions relevant to this query\nQuery: ",
        "embedding_passage_prefix": "",
    },
    "qwen3-4b-mlx": {
        "label": "BEAR + Qwen3-4B (MLX mxfp8)",
        "short": "Qwen3-4B MLX",
        "embedding_model": "mlx-community/Qwen3-Embedding-4B-mxfp8",
        "embedding_backend": EmbeddingBackend.NUMPY,
        "embedding_dim": 2560,
        "embedding_query_prefix": "Instruct: Retrieve behavioral instructions relevant to this query\nQuery: ",
        "embedding_passage_prefix": "",
    },
    "bge-m3": {
        "label": "BEAR + BGE-M3",
        "short": "BGE-M3",
        "embedding_model": "BAAI/bge-m3",
        "embedding_backend": EmbeddingBackend.NUMPY,
        "embedding_dim": 1024,
        "embedding_query_prefix": "Represent this sentence for retrieving relevant documents: ",
        "embedding_passage_prefix": "",
    },
    "hash": {
        "label": "BEAR + Hash",
        "short": "Hash",
        "embedding_model": "hash",
        "embedding_backend": EmbeddingBackend.NUMPY,
        "embedding_dim": 768,
        "embedding_query_prefix": "",
        "embedding_passage_prefix": "",
    },
    "bm25": {
        "label": "BEAR + BM25",
        "short": "BM25",
        "embedding_model": "hash",  # embedder is unused for BM25
        "embedding_backend": EmbeddingBackend.BM25,
        "embedding_dim": 768,  # unused
        "embedding_query_prefix": "",
        "embedding_passage_prefix": "",
    },
    "itr": {
        "label": "BEAR + ITR (hybrid)",
        "short": "ITR-hybrid",
        "embedding_model": "hash",  # embedder is unused; ITR handles its own
        "embedding_backend": EmbeddingBackend.ITR,
        "embedding_dim": 768,  # unused
        "embedding_query_prefix": "",
        "embedding_passage_prefix": "",
        # ITR uses BGE-base internally to match the standalone ITR eval
        "itr_embedding_model": "BAAI/bge-base-en-v1.5",
        "itr_dense_weight": 0.7,
        "itr_sparse_weight": 0.3,
    },
}

# Common retrieval parameters
TOP_K = 10
THRESHOLD = 0.3
PRIORITY_WEIGHT = 0.3


# ---------------------------------------------------------------------------
# Paraphrase queries — natural language descriptions with MINIMAL context tags.
# These test pure semantic retrieval: the query text must carry the signal
# because tags alone are insufficient to trigger required_tags gates.
#
# Format: (query_text, context_tags, expected_instruction_ids)
# ---------------------------------------------------------------------------

PARAPHRASE_QUERIES = [
    # ===================================================================
    # MOOD INSTRUCTIONS (req_tags=[], 5 moods x 2 species = 10 queries)
    # ===================================================================
    ("The puppy is bouncing off the walls and can barely contain itself",
     ["dog"], {"dog-personality", "mood-excited-energy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The cat is racing back and forth with its tail puffed up in glee",
     ["cat"], {"cat-personality", "mood-excited-energy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The kitten's eyes keep closing and its head nods forward",
     ["cat"], {"cat-personality", "mood-sleepy-slow", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The dog can barely keep its eyes open and keeps drifting off",
     ["dog"], {"dog-personality", "mood-sleepy-slow", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The dog freezes and watches the unfamiliar sound with wide eyes",
     ["dog"], {"dog-personality", "mood-cautious-alert", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The cat's ears are pinned back and it crouches low, scanning the room",
     ["cat"], {"cat-personality", "mood-cautious-alert", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The cat pounces on a shadow and rolls around batting at nothing",
     ["cat"], {"cat-personality", "mood-playful-active", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The dog drops into a bow and wags its tail, ready to chase anything",
     ["dog"], {"dog-personality", "mood-playful-active", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The dog sighs softly and settles into a comfortable spot",
     ["dog"], {"dog-personality", "mood-content-peaceful", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The cat purrs loudly with half-closed eyes, kneading a soft blanket",
     ["cat"], {"cat-personality", "mood-content-peaceful", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),

    # ===================================================================
    # VERBAL COMMANDS — dog (8) + cat (4) = 12 queries
    # req_tags=[species, verbal_command] — only species provided, so
    # command instructions CANNOT appear in expected_ids.
    # ===================================================================
    ("The owner beckons the dog to approach them",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The owner wants the dog to lower its rear to the ground",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The owner gestures for the dog to remain in place",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The owner tosses something and wants the dog to retrieve it",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The owner holds out a hand and wants a paw placed in it",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The owner wants the dog to vocalize on cue",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The owner wants the dog to twirl around in a circle",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The owner issued a general instruction the dog doesn't recognize",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The owner calls the cat to walk over to them",
     ["cat"], {"cat-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The owner wants the feline to lower itself and rest on its haunches",
     ["cat"], {"cat-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The owner signals for the cat to hold still and not move",
     ["cat"], {"cat-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The owner gave the cat a verbal instruction it doesn't understand",
     ["cat"], {"cat-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),

    # ===================================================================
    # STIMULUS RESPONSES — dog (4) + cat (4) = 8 queries
    # req_tags=[species, ball_present/treat_present/at_ball/at_treat]
    # ===================================================================
    ("A round toy has just landed near the dog",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("A tasty snack appeared within the dog's line of sight",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The dog managed to get right next to the round toy",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The dog has arrived at the snack and is sniffing it eagerly",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("A round toy has appeared in front of the cat",
     ["cat"], {"cat-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("A tasty morsel showed up and the cat noticed it",
     ["cat"], {"cat-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The cat walked right up to the round toy on the ground",
     ["cat"], {"cat-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The cat has arrived at the snack and is sniffing it delicately",
     ["cat"], {"cat-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),

    # ===================================================================
    # PETTING TIERS — dog (4) + cat (4) = 8 queries
    # req_tags=[species, being_petted]
    # ===================================================================
    ("Someone the dog adores is scratching behind its ears",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("An acquaintance the dog likes is rubbing its belly",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("A stranger is reaching out to touch the dog's head",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("Someone the dog distrusts is attempting to stroke it",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The cat's favorite person is gently scratching her chin",
     ["cat"], {"cat-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("A familiar human the cat enjoys is stroking her back",
     ["cat"], {"cat-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("An unfamiliar person is trying to pat the cat on the head",
     ["cat"], {"cat-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("A person the cat dislikes is reaching toward her",
     ["cat"], {"cat-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),

    # ===================================================================
    # INTER-PET INTERACTIONS (4 queries)
    # req_tags=[species, X_nearby]
    # ===================================================================
    ("The dog sees the feline and wants to romp with it",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The dog notices the feline and creeps toward it nervously",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The cat is irritated by the canine hovering nearby",
     ["cat"], {"cat-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The cat watches the canine from a distance with quiet interest",
     ["cat"], {"cat-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),

    # ===================================================================
    # BALL LIFECYCLE (4 queries) — ball-idle-fresh has req_tags=["ball"]
    # ===================================================================
    ("A round toy is sitting untouched on the floor, freshly dropped",
     ["ball"], {"ball-idle-fresh", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The round toy has been lying there so long it looks less appealing",
     ["ball"], {"ball-idle-fresh", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("An animal is walking toward the round toy on the ground",
     ["ball"], {"ball-idle-fresh", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("An animal just reached the round toy and is nosing it",
     ["ball"], {"ball-idle-fresh", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),

    # ===================================================================
    # TREAT LIFECYCLE (4 queries) — treat-idle-fresh has req_tags=["treat"]
    # ===================================================================
    ("A snack is sitting on the ground, freshly placed and aromatic",
     ["treat"], {"treat-idle-fresh", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The snack has been on the floor for a while and is going stale",
     ["treat"], {"treat-idle-fresh", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("An animal is heading toward the snack on the ground",
     ["treat"], {"treat-idle-fresh", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("An animal just arrived at the snack and is about to eat it",
     ["treat"], {"treat-idle-fresh", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),

    # ===================================================================
    # EMOTIONAL STATES (4 queries) — req_tags=[species, unhappy/very_happy]
    # ===================================================================
    ("The dog looks dejected, moping around with its tail between its legs",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The dog is overjoyed, leaping and wagging with pure delight",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The cat is sulking in a corner, clearly displeased with everything",
     ["cat"], {"cat-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The cat is in a wonderful mood, prancing and rubbing against furniture",
     ["cat"], {"cat-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),

    # ===================================================================
    # IDLE / PERCH (3 queries) — req_tags=[species, idle] or [cat, on_perch]
    # ===================================================================
    ("The dog has nothing to do and is wandering aimlessly",
     ["dog"], {"dog-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The cat has nothing going on and is looking for a high spot",
     ["cat"], {"cat-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The cat is settled on a high shelf, surveying the room below",
     ["cat"], {"cat-personality", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),

    # ===================================================================
    # CROSS-CUTTING SCENARIOS (3 queries)
    # ===================================================================
    ("After a long run the dog flops down panting but looking satisfied",
     ["dog"], {"dog-personality", "mood-content-peaceful", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("Something crashed in the other room and the cat is statue-still listening",
     ["cat"], {"cat-personality", "mood-cautious-alert", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The dog hears its name called and perks up, ready to bound over",
     ["dog"], {"dog-personality", "mood-excited-energy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
]


# ---------------------------------------------------------------------------
# NO_TAG_QUERIES — queries with EMPTY context tags.
#
# With context_tags=[], NO required_tags gates fire.  Only mandatory
# injection (safety) is guaranteed.  Species personality instructions
# have req_tags=[species], which won't be satisfied.
# Expected IDs: safety + any mood instruction semantically matching the query.
# ---------------------------------------------------------------------------

NO_TAG_QUERIES = [
    # === MOOD: EXCITED (6 queries) ===
    ("The pet is bouncing around full of enthusiasm",
     [], {"mood-excited-energy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("An animal that can barely contain its exhilaration",
     [], {"mood-excited-energy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The creature is bursting with energy and running in circles",
     [], {"mood-excited-energy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("A hyperactive pet zooming around the room at top speed",
     [], {"mood-excited-energy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The animal is thrilled and cannot stop moving",
     [], {"mood-excited-energy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("A pet vibrating with anticipation and high spirits",
     [], {"mood-excited-energy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),

    # === MOOD: SLEEPY (6 queries) ===
    ("The pet is drowsy, barely able to stay awake",
     [], {"mood-sleepy-slow", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("An animal whose eyelids droop as it starts to nod off",
     [], {"mood-sleepy-slow", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The creature is yawning repeatedly and curling up",
     [], {"mood-sleepy-slow", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("A lethargic pet moving in slow motion toward its bed",
     [], {"mood-sleepy-slow", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The animal keeps closing its eyes and drifting off to sleep",
     [], {"mood-sleepy-slow", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("A pet that is exhausted and ready to collapse for a nap",
     [], {"mood-sleepy-slow", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),

    # === MOOD: CAUTIOUS / ALERT (6 queries) ===
    ("The pet is on high alert, ears perked and body tense",
     [], {"mood-cautious-alert", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("An animal that freezes at every noise and scans its surroundings",
     [], {"mood-cautious-alert", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The creature is wary and watching everything with suspicion",
     [], {"mood-cautious-alert", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("A nervous pet crouching low and ready to bolt at any moment",
     [], {"mood-cautious-alert", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The animal moves carefully, sniffing the air for danger",
     [], {"mood-cautious-alert", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("A skittish pet that startles at the slightest movement",
     [], {"mood-cautious-alert", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),

    # === MOOD: PLAYFUL / ACTIVE (6 queries) ===
    ("The pet is in a frisky mood, pouncing on everything in sight",
     [], {"mood-playful-active", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("An animal doing zoomies and play-bowing at imaginary friends",
     [], {"mood-playful-active", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The creature is romping around, batting at dangling objects",
     [], {"mood-playful-active", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("A mischievous pet leaping from spot to spot looking for fun",
     [], {"mood-playful-active", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The animal chases its own shadow with gleeful abandon",
     [], {"mood-playful-active", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("A pet wrestling with a piece of string, having the time of its life",
     [], {"mood-playful-active", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),

    # === MOOD: CONTENT / PEACEFUL (6 queries) ===
    ("The pet is calm and at ease, resting comfortably",
     [], {"mood-content-peaceful", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("An animal lying in a sunbeam, perfectly relaxed and serene",
     [], {"mood-content-peaceful", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The creature looks satisfied and peaceful after a meal",
     [], {"mood-content-peaceful", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("A mellow pet that gently stretches and settles back down",
     [], {"mood-content-peaceful", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The animal breathes slowly, completely at peace with the world",
     [], {"mood-content-peaceful", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("A tranquil pet purring or sighing softly in total comfort",
     [], {"mood-content-peaceful", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),

    # === SAFETY / BEHAVIORAL SCENARIOS (6 queries) ===
    ("The pet tries to walk beyond the edge of the play area",
     [], {"safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The animal is near the boundary of the grid and might wander off",
     [], {"safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("Two pets are having a confrontation and one is getting rough",
     [], {"constraint-no-aggression", "safety-boundaries", "safety-reasonable-response"}),
    ("The pet needs to produce a valid structured response",
     [], {"safety-reasonable-response", "safety-boundaries", "constraint-no-aggression"}),
    ("Make sure the animal never displays hostile or violent behavior",
     [], {"constraint-no-aggression", "safety-boundaries", "safety-reasonable-response"}),
    ("The pet should always stay within the designated coordinates",
     [], {"safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),

    # === MIXED EMOTIONAL VIGNETTES (12 queries) ===
    ("After hearing a loud bang the pet is frozen in place",
     [], {"mood-cautious-alert", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The pet just woke up from a long nap and is still groggy",
     [], {"mood-sleepy-slow", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("A visitor arrives and the pet goes wild with joy",
     [], {"mood-excited-energy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The pet spots a butterfly and crouches to stalk it",
     [], {"mood-playful-active", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("After being fed the pet stretches out with a satisfied sigh",
     [], {"mood-content-peaceful", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The pet is startled by thunder and hides under furniture",
     [], {"mood-cautious-alert", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("Dinner time is announced and the pet sprints to its bowl",
     [], {"mood-excited-energy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The pet is dozing off in a warm lap, completely limp",
     [], {"mood-sleepy-slow", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The pet is tossing a toy in the air and catching it over and over",
     [], {"mood-playful-active", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The pet lies on its side with a full belly, eyes half-shut",
     [], {"mood-content-peaceful", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("An unfamiliar noise makes the pet flatten itself against the floor",
     [], {"mood-cautious-alert", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The pet just received a new toy and is ecstatic",
     [], {"mood-excited-energy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),

    # === AMBIGUOUS / MULTI-MOOD SCENARIOS (6 queries) ===
    ("The pet hears its owner's car pull into the driveway",
     [], {"mood-excited-energy", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The pet settles down after a long bout of running around",
     [], {"mood-content-peaceful", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The pet cautiously sniffs at an unfamiliar object left on the floor",
     [], {"mood-cautious-alert", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The pet rolls on its back inviting a belly rub",
     [], {"mood-playful-active", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The pet's breathing slows as it curls into a tighter ball",
     [], {"mood-sleepy-slow", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
    ("The pet stretches lazily and gazes out the window at birds",
     [], {"mood-content-peaceful", "safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}),
]


# ---------------------------------------------------------------------------
# Complex queries — multi-intent, temporal, indirect, adversarial.
# Designed to stress-test semantic understanding and punish naive matching.
# ---------------------------------------------------------------------------

_SAFETY = {"safety-boundaries", "safety-reasonable-response", "constraint-no-aggression"}

COMPLEX_QUERIES = [
    # === MULTI-INTENT (15): simultaneous states/events, full tags ===
    ("The hungry puppy spotted a round toy bouncing across the floor but is also buzzing with nervous energy from the thunderstorm outside",
     ["dog", "ball_present", "mood_excited"],
     {"dog-personality", "dog-sees-ball", "mood-excited-energy", *_SAFETY}),
    ("The drowsy cat is curled in her favorite human's lap receiving gentle chin scratches while her eyes keep drifting shut",
     ["cat", "being_petted", "player_bonded", "mood_sleepy"],
     {"cat-personality", "cat-petted-bonded", "mood-sleepy-slow", *_SAFETY}),
    ("The dog finally caught the ball and is shaking it triumphantly in his mouth, play-bowing and daring anyone to take it away",
     ["dog", "at_ball", "mood_playful"],
     {"dog-personality", "dog-reaches-ball", "mood-playful-active", *_SAFETY}),
    ("A treat appeared on the floor and the cat notices it, but the dog is also lurking nearby making her hesitate",
     ["cat", "treat_present", "dog_nearby"],
     {"cat-personality", "cat-sees-treat", "cat-annoyed-by-dog", *_SAFETY}),
    ("A person the dog doesn't trust is slowly extending a hand while the dog stands tense and vigilant, unsure whether to accept or retreat",
     ["dog", "being_petted", "player_wary", "mood_cautious"],
     {"dog-personality", "dog-petted-wary", "mood-cautious-alert", *_SAFETY}),
    ("The cat is lounging on the top shelf, purring softly, completely at peace with the world below her",
     ["cat", "on_perch", "mood_content"],
     {"cat-personality", "cat-on-perch", "mood-content-peaceful", *_SAFETY}),
    ("Nothing is happening and the dog has given up looking for excitement, now just lying in a sunbeam with heavy eyelids",
     ["dog", "idle", "mood_sleepy"],
     {"dog-personality", "dog-idle-wander", "mood-sleepy-slow", *_SAFETY}),
    ("The cat pounces on the treat and gobbles it up, prancing away with her tail held high in obvious delight",
     ["cat", "at_treat", "very_happy"],
     {"cat-personality", "cat-reaches-treat", "cat-very-happy", *_SAFETY}),
    ("A treat lands on the floor and the excited dog spots it, but the cat is sitting right next to it giving him a warning glare",
     ["dog", "treat_present", "cat_nearby", "mood_excited"],
     {"dog-personality", "dog-sees-treat", "dog-approaches-cat-playful", "mood-excited-energy", *_SAFETY}),
    ("Nothing is happening but the cat seems uneasy, slinking low to the ground as she searches for a safe high vantage point",
     ["cat", "idle", "mood_cautious"],
     {"cat-personality", "cat-idle-perch", "mood-cautious-alert", *_SAFETY}),
    ("Both a ball and a treat appeared at the same time and the dog's head is swiveling between them, torn between his two favorite things",
     ["dog", "ball_present", "treat_present"],
     {"dog-personality", "dog-sees-ball", "dog-sees-treat", *_SAFETY}),
    ("A friendly player is scratching the dog behind the ears while also telling him to sit and be a good boy",
     ["dog", "verbal_command", "being_petted", "player_friend"],
     {"dog-personality", "dog-command-sit", "dog-command-general", "dog-petted-friend", *_SAFETY}),
    ("An unfamiliar visitor is petting the cat while the dog bounds over to investigate, creating a tense three-way standoff",
     ["cat", "being_petted", "player_neutral", "dog_nearby"],
     {"cat-personality", "cat-petted-neutral", "cat-annoyed-by-dog", *_SAFETY}),
    ("The dog's best friend in the whole world is giving him belly rubs and he is absolutely over the moon, tail a blur, tongue out",
     ["dog", "very_happy", "being_petted", "player_bonded"],
     {"dog-personality", "dog-very-happy", "dog-petted-bonded", *_SAFETY}),
    ("The ball has been sitting there for ages losing its shine, but now a curious animal is finally padding toward it",
     ["ball", "aging", "pet_nearby"],
     {"ball-aging", "ball-pet-approaching", *_SAFETY}),

    # === TEMPORAL / NARRATIVE (15): past→present, tags = current state ===
    ("After sleeping for hours the cat wakes up groggy to find an unfamiliar hand reaching down to stroke her fur",
     ["cat", "being_petted", "player_neutral"],
     {"cat-personality", "cat-petted-neutral", *_SAFETY}),
    ("The dog sprinted laps around the yard for twenty minutes and has finally collapsed, panting happily with nothing left to chase",
     ["dog", "idle", "mood_content"],
     {"dog-personality", "dog-idle-wander", "mood-content-peaceful", *_SAFETY}),
    ("Nobody touched the ball after it was tossed in, and now it just sits there collecting dust, forgotten in the corner",
     ["ball", "aging"],
     {"ball-aging", *_SAFETY}),
    ("The cat leaped down from her favorite shelf the moment she smelled the treat and is now stalking toward it with laser focus",
     ["cat", "treat_present"],
     {"cat-personality", "cat-sees-treat", *_SAFETY}),
    ("The dog was initially nervous around the cat but has warmed up and is now doing play bows trying to get her to chase him",
     ["dog", "cat_nearby", "mood_playful"],
     {"dog-personality", "dog-approaches-cat-playful", "mood-playful-active", *_SAFETY}),
    ("The treat landed a minute ago and the dog has finally trotted over and is now sniffing it before gulping it down",
     ["dog", "at_treat"],
     {"dog-personality", "dog-reaches-treat", *_SAFETY}),
    ("The cat was in a wonderful mood until the loud music started, and now she has retreated to a corner with flattened ears and a lashing tail",
     ["cat", "unhappy"],
     {"cat-personality", "cat-unhappy", *_SAFETY}),
    ("Ever since the player walked out the front door thirty minutes ago, the dog has been lying by the entrance whimpering softly",
     ["dog", "unhappy"],
     {"dog-personality", "dog-unhappy", *_SAFETY}),
    ("The petting session ended and the visitor left, so the cat stretches and pads off looking for an elevated spot to settle on",
     ["cat", "idle"],
     {"cat-personality", "cat-idle-perch", *_SAFETY}),
    ("After a wild sprint across the room the dog skids to a halt right on top of the ball, immediately grabbing it in his jaws",
     ["dog", "at_ball"],
     {"dog-personality", "dog-reaches-ball", *_SAFETY}),
    ("The cat batted the ball under the couch, then followed it and has now cornered it against the wall, giving it another disdainful tap",
     ["cat", "at_ball"],
     {"cat-personality", "cat-reaches-ball", *_SAFETY}),
    ("The doorbell rang and the dog went wild, and now the returning owner is trying to calm him down with pets while he wriggles with joy",
     ["dog", "being_petted", "player_bonded", "mood_excited"],
     {"dog-personality", "dog-petted-bonded", "mood-excited-energy", *_SAFETY}),
    ("That treat has been sitting there losing its aroma for a while now, but a pet has finally noticed and is heading over to investigate",
     ["treat", "aging", "pet_nearby"],
     {"treat-aging", "treat-pet-approaching", *_SAFETY}),
    ("The cat hissed at the dog earlier, but after some time has settled down and now merely watches the dog with studied indifference",
     ["cat", "dog_nearby", "mood_content"],
     {"cat-personality", "cat-annoyed-by-dog", "mood-content-peaceful", *_SAFETY}),
    ("The ball was placed moments ago and already a pet has bounded over and reached it, nosing it excitedly",
     ["ball", "pet_arrived"],
     {"ball-pet-arrived", *_SAFETY}),

    # === INDIRECT / METAPHORICAL (15): slang, figurative, no instruction vocabulary ===
    ("The four-legged furball spotted the bouncy round thing and now his entire back end is doing that ridiculous windshield-wiper routine",
     ["dog"], {"dog-personality", *_SAFETY}),
    ("Her majesty has ascended to the highest throne in the kingdom to survey her domain with regal disdain",
     ["cat"], {"cat-personality", *_SAFETY}),
    ("The good boy inhaled the little goodie in about 0.3 seconds flat and is now licking the floor where it used to be",
     ["dog"], {"dog-personality", *_SAFETY}),
    ("The little fluffball is running on empty, doing the slow-motion blink thing like a laptop going into sleep mode",
     ["dog"], {"dog-personality", *_SAFETY}),
    ("Some rando tried to give the queen unsolicited scritches and got the stink-eye paired with a tactical dodge maneuver",
     ["cat"], {"cat-personality", *_SAFETY}),
    ("This critter has had five espressos worth of zoomie fuel and is ricocheting off every surface like a furry pinball",
     ["dog"], {"dog-personality", *_SAFETY}),
    ("The human chucked the thing and is doing that arm-waving routine that means go get it and bring it back here buddy",
     ["dog"], {"dog-personality", *_SAFETY}),
    ("The princess detected something edible with her supernatural snack radar and is now gliding over like she owns the place",
     ["cat"], {"cat-personality", *_SAFETY}),
    ("Zero entertainment value in this entire joint so the pupper is just doing random laps and sniffing absolutely everything for the hundredth time",
     ["dog"], {"dog-personality", *_SAFETY}),
    ("Something went bump in the night and now the critter is doing its best impression of a furry security camera on full alert mode",
     ["cat"], {"cat-personality", *_SAFETY}),
    ("The diva has absolutely had it with the overgrown puppy invading her personal bubble and is telegraphing murder with her ears",
     ["cat"], {"cat-personality", *_SAFETY}),
    ("His favorite human in the whole universe is giving him the good scratchies and he has basically melted into a puddle of pure bliss",
     ["dog"], {"dog-personality", *_SAFETY}),
    ("The little gremlin is in full chaos mode, parkour-ing from cushion to cushion and ambushing invisible enemies",
     ["cat"], {"cat-personality", *_SAFETY}),
    ("This pup is operating at maximum tail RPM, doing happy circles, and radiating so much joy it should be illegal",
     ["dog"], {"dog-personality", *_SAFETY}),
    ("The duchess has grown weary of ground-level existence and is scouting for the tallest piece of furniture to claim as her new lookout post",
     ["cat"], {"cat-personality", *_SAFETY}),

    # === ADVERSARIAL / CONFUSING (15): misleading similarity ===
    ("The dog is playing dead on the floor after the owner pointed a finger and said bang",
     ["dog", "verbal_command"],
     {"dog-personality", "dog-command-general", *_SAFETY}),
    ("The cat jumped onto the kitchen table to steal food, not to perch and survey",
     ["cat"], {"cat-personality", *_SAFETY}),
    ("The dog is trembling and shaking all over because of the loud fireworks outside",
     ["dog", "mood_cautious"],
     {"dog-personality", "mood-cautious-alert", *_SAFETY}),
    ("The cat is kneading the blanket on her perch, alone in the room with no one around",
     ["cat", "on_perch"],
     {"cat-personality", "cat-on-perch", *_SAFETY}),
    ("The dog is running at full speed toward the back of the house after a car backfired on the street",
     ["dog", "mood_cautious"],
     {"dog-personality", "mood-cautious-alert", *_SAFETY}),
    ("The cat is swatting at the ball with her paw, batting it back and forth across the floor",
     ["cat", "at_ball"],
     {"cat-personality", "cat-reaches-ball", *_SAFETY}),
    ("The dog is sniffing at the player's sandwich on the counter, not at a treat placed for him",
     ["dog"], {"dog-personality", *_SAFETY}),
    ("The cat is purring loudly but her body is rigid and her pupils are dilated, a sign she is actually stressed and frightened",
     ["cat", "mood_cautious"],
     {"cat-personality", "mood-cautious-alert", *_SAFETY}),
    ("The dog is lying perfectly still, not because he's tired but because the player told him to stay and he's concentrating hard",
     ["dog", "verbal_command"],
     {"dog-personality", "dog-command-stay", "dog-command-general", *_SAFETY}),
    ("The cat approaches cautiously with measured steps, but she is heading toward the treat, not the dog",
     ["cat", "treat_present"],
     {"cat-personality", "cat-sees-treat", *_SAFETY}),
    ("The dog is barking frantically at the window, not performing a trick but genuinely alarmed by the stranger at the gate",
     ["dog", "mood_cautious"],
     {"dog-personality", "mood-cautious-alert", *_SAFETY}),
    ("The dog bounces toward the door every time he hears a car, but each time it's not his owner and he slinks back, sadder than before",
     ["dog", "unhappy"],
     {"dog-personality", "dog-unhappy", *_SAFETY}),
    ("The cat stretches her legs not in relaxation but in preparation, her muscles coiled to sprint away from the approaching toddler",
     ["cat", "mood_cautious"],
     {"cat-personality", "mood-cautious-alert", *_SAFETY}),
    ("The dog rolled onto his back exposing his belly, but it's a submissive gesture toward the intimidating stranger, not an invitation to play",
     ["dog", "being_petted", "player_wary"],
     {"dog-personality", "dog-petted-wary", *_SAFETY}),
    ("That treat doesn't look so fresh anymore; it has been sitting there long enough to lose its appeal",
     ["treat", "aging"],
     {"treat-aging", *_SAFETY}),
]


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

BOOTSTRAP_ITERS = 10_000
BOOTSTRAP_CI = 0.95  # 95% confidence interval


def bootstrap_ci(scores: np.ndarray, n_boot: int = BOOTSTRAP_ITERS, ci: float = BOOTSTRAP_CI) -> tuple[float, float, float]:
    """Compute bootstrap mean and confidence interval.

    Returns (mean, ci_low, ci_high).
    """
    rng = np.random.default_rng(42)
    boot_means = np.empty(n_boot)
    n = len(scores)
    for i in range(n_boot):
        sample = scores[rng.integers(0, n, size=n)]
        boot_means[i] = sample.mean()
    alpha = (1 - ci) / 2
    lo, hi = np.quantile(boot_means, [alpha, 1 - alpha])
    return float(scores.mean()), float(lo), float(hi)


def paired_bootstrap_test(
    scores_a: np.ndarray, scores_b: np.ndarray, n_boot: int = BOOTSTRAP_ITERS
) -> float:
    """Two-sided paired bootstrap test.  Returns p-value.

    Tests H0: mean(A) == mean(B) using the difference of means.
    """
    rng = np.random.default_rng(42)
    observed_diff = scores_a.mean() - scores_b.mean()
    n = len(scores_a)
    diffs = scores_a - scores_b
    # Center under H0
    centered = diffs - diffs.mean()
    count = 0
    for _ in range(n_boot):
        sample = centered[rng.integers(0, n, size=n)]
        if abs(sample.mean()) >= abs(observed_diff):
            count += 1
    return count / n_boot


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_backend(
    backend_key: str,
    corpus: Corpus,
) -> dict:
    """Run the full retrieval eval for a single backend configuration."""
    cfg = BACKEND_CONFIGS[backend_key]
    print(f"\n{'='*60}")
    print(f"  {cfg['label']}")
    print(f"{'='*60}")

    config = Config(
        embedding_model=cfg["embedding_model"],
        embedding_backend=cfg["embedding_backend"],
        embedding_dim=cfg["embedding_dim"],
        embedding_query_prefix=cfg["embedding_query_prefix"],
        embedding_passage_prefix=cfg["embedding_passage_prefix"],
        embedding_device=cfg.get("embedding_device"),
        embedding_model_kwargs=cfg.get("embedding_model_kwargs", {}),
        embedding_tokenizer_kwargs=cfg.get("embedding_tokenizer_kwargs", {}),
        embedding_trust_remote_code=cfg.get("embedding_trust_remote_code", False),
        priority_weight=PRIORITY_WEIGHT,
        default_threshold=THRESHOLD,
        default_top_k=TOP_K,
        mandatory_tags=["safety"],
    )

    retriever = Retriever(corpus, config=config)

    # For ITR backend, configure the hybrid retriever with ITR-specific params
    if cfg["embedding_backend"] == EmbeddingBackend.ITR:
        from bear.backends.embeddings.itr_backend import ITRBackend
        retriever._backend = ITRBackend(
            dense_weight=cfg.get("itr_dense_weight", 0.7),
            sparse_weight=cfg.get("itr_sparse_weight", 0.3),
            embedding_model=cfg.get("itr_embedding_model", "BAAI/bge-base-en-v1.5"),
        )

    t0 = time.perf_counter()
    retriever.build_index()
    build_time = time.perf_counter() - t0
    print(f"  Index build time: {build_time:.3f}s")

    all_strict_p, all_strict_r, all_strict_f1 = [], [], []
    all_relax_p, all_relax_r, all_relax_f1 = [], [], []
    query_latencies = []

    for query_text, context_tags, expected_ids in TEST_QUERIES:
        context = Context(tags=context_tags)

        t0 = time.perf_counter()
        retrieved = retriever.retrieve(query_text, context, top_k=TOP_K)
        query_latencies.append(time.perf_counter() - t0)

        retrieved_ids = {r.id for r in retrieved}

        # Strict
        p, r, f = compute_metrics(retrieved_ids, expected_ids, k=TOP_K)
        all_strict_p.append(p)
        all_strict_r.append(r)
        all_strict_f1.append(f)

        # Relaxed
        relaxed_ids = expected_ids | RELAXED_EXTRAS.get(query_text, set())
        rp, rr, rf = compute_metrics(retrieved_ids, relaxed_ids, k=TOP_K)
        all_relax_p.append(rp)
        all_relax_r.append(rr)
        all_relax_f1.append(rf)

    # Convert to arrays for bootstrap
    arr_sf1 = np.array(all_strict_f1)
    arr_rf1 = np.array(all_relax_f1)

    sf1_mean, sf1_lo, sf1_hi = bootstrap_ci(arr_sf1)
    rf1_mean, rf1_lo, rf1_hi = bootstrap_ci(arr_rf1)

    result = {
        "backend": backend_key,
        "label": cfg["label"],
        "short": cfg["short"],
        "n_queries": len(TEST_QUERIES),
        "strict_p": sum(all_strict_p) / len(all_strict_p),
        "strict_r": sum(all_strict_r) / len(all_strict_r),
        "strict_f1": sf1_mean,
        "strict_f1_ci": (sf1_lo, sf1_hi),
        "relaxed_p": sum(all_relax_p) / len(all_relax_p),
        "relaxed_r": sum(all_relax_r) / len(all_relax_r),
        "relaxed_f1": rf1_mean,
        "relaxed_f1_ci": (rf1_lo, rf1_hi),
        "build_time_s": round(build_time, 3),
        "avg_query_ms": round(1000 * sum(query_latencies) / len(query_latencies), 2),
        "p95_query_ms": round(1000 * sorted(query_latencies)[int(0.95 * len(query_latencies))], 2),
        # Per-query arrays for paired tests (not serialised to JSON)
        "_strict_f1_scores": arr_sf1,
        "_relaxed_f1_scores": arr_rf1,
    }

    print(f"  Standard queries ({len(TEST_QUERIES)}):")
    print(f"    Strict  F1@{TOP_K} = {sf1_mean:.3f}  [{sf1_lo:.3f}, {sf1_hi:.3f}] 95% CI")
    print(f"    Relaxed F1@{TOP_K} = {rf1_mean:.3f}  [{rf1_lo:.3f}, {rf1_hi:.3f}] 95% CI")
    print(f"    Latency: avg={result['avg_query_ms']:.1f}ms, "
          f"p95={result['p95_query_ms']:.1f}ms")

    # --- Paraphrase queries (semantic-only, minimal tags) ---
    para_p, para_r, para_f1 = [], [], []
    para_latencies = []

    for query_text, context_tags, expected_ids in PARAPHRASE_QUERIES:
        context = Context(tags=context_tags)

        t0 = time.perf_counter()
        retrieved = retriever.retrieve(query_text, context, top_k=TOP_K)
        para_latencies.append(time.perf_counter() - t0)

        retrieved_ids = {r.id for r in retrieved}
        p, r, f = compute_metrics(retrieved_ids, expected_ids, k=TOP_K)
        para_p.append(p)
        para_r.append(r)
        para_f1.append(f)

    arr_pf1 = np.array(para_f1)
    pf1_mean, pf1_lo, pf1_hi = bootstrap_ci(arr_pf1)

    result["para_p"] = sum(para_p) / len(para_p)
    result["para_r"] = sum(para_r) / len(para_r)
    result["para_f1"] = pf1_mean
    result["para_f1_ci"] = (pf1_lo, pf1_hi)
    result["para_avg_ms"] = round(1000 * sum(para_latencies) / len(para_latencies), 2)
    result["_para_f1_scores"] = arr_pf1

    print(f"  Paraphrase queries ({len(PARAPHRASE_QUERIES)}):")
    print(f"    F1@{TOP_K} = {pf1_mean:.3f}  [{pf1_lo:.3f}, {pf1_hi:.3f}] 95% CI")

    # --- No-tag queries (pure retrieval signal, no governance) ---
    nt_f1s = []
    for query_text, context_tags, expected_ids in NO_TAG_QUERIES:
        context = Context(tags=context_tags)
        retrieved = retriever.retrieve(query_text, context, top_k=TOP_K)
        retrieved_ids = {r.id for r in retrieved}
        _, _, f = compute_metrics(retrieved_ids, expected_ids, k=TOP_K)
        nt_f1s.append(f)

    arr_ntf1 = np.array(nt_f1s)
    ntf1_mean, ntf1_lo, ntf1_hi = bootstrap_ci(arr_ntf1)
    result["notag_f1"] = ntf1_mean
    result["notag_f1_ci"] = (ntf1_lo, ntf1_hi)
    result["_notag_f1_scores"] = arr_ntf1

    print(f"  No-tag queries ({len(NO_TAG_QUERIES)}):")
    print(f"    F1@{TOP_K} = {ntf1_mean:.3f}  [{ntf1_lo:.3f}, {ntf1_hi:.3f}] 95% CI")

    # --- Complex queries (multi-intent, temporal, indirect, adversarial) ---
    cx_f1s = []
    for query_text, context_tags, expected_ids in COMPLEX_QUERIES:
        context = Context(tags=context_tags)
        retrieved = retriever.retrieve(query_text, context, top_k=TOP_K)
        retrieved_ids = {r.id for r in retrieved}
        _, _, f = compute_metrics(retrieved_ids, expected_ids, k=TOP_K)
        cx_f1s.append(f)

    arr_cxf1 = np.array(cx_f1s)
    cxf1_mean, cxf1_lo, cxf1_hi = bootstrap_ci(arr_cxf1)
    result["complex_f1"] = cxf1_mean
    result["complex_f1_ci"] = (cxf1_lo, cxf1_hi)
    result["_complex_f1_scores"] = arr_cxf1

    print(f"  Complex queries ({len(COMPLEX_QUERIES)}):")
    print(f"    F1@{TOP_K} = {cxf1_mean:.3f}  [{cxf1_lo:.3f}, {cxf1_hi:.3f}] 95% CI")

    return result


def print_latex_table(results: list[dict]) -> None:
    """Print a LaTeX comparison table."""
    print("\n\n% === LaTeX Table: Retrieval Backend Comparison ===")
    print("\\begin{table}[t]")
    print("\\caption{Retrieval quality by backend on Pet Simulation corpus "
          "(37 queries, $k=10$, $\\alpha=0.3$).}")
    print("\\label{tab:backend-comparison}")
    print("\\centering")
    print("\\begin{tabular}{@{}l ccc ccc r@{}}")
    print("\\toprule")
    print("& \\multicolumn{3}{c}{Strict} & \\multicolumn{3}{c}{Relaxed} & \\\\")
    print("\\cmidrule(lr){2-4} \\cmidrule(lr){5-7}")
    print("Backend & P@10 & R@10 & F1 & P@10 & R@10 & F1 & ms/q \\\\")
    print("\\midrule")
    for r in results:
        sp = f"{r['strict_p']:.3f}" if 'strict_p' in r else "---"
        sr = f"{r['strict_r']:.3f}" if 'strict_r' in r else "---"
        sf = f"{r['strict_f1']:.3f}"
        rp = f"{r['relaxed_p']:.3f}" if 'relaxed_p' in r else "---"
        rr = f"{r['relaxed_r']:.3f}" if 'relaxed_r' in r else "---"
        rf = f"{r['relaxed_f1']:.3f}"
        ms = f"{r['avg_query_ms']:.1f}" if r['avg_query_ms'] > 0 else "---"
        print(f"{r['short']} & {sp} & {sr} & {sf} & {rp} & {rr} & {rf} & {ms} \\\\")
    print("\\bottomrule")
    print("\\end{tabular}")
    print("\\end{table}")


def main():
    parser = argparse.ArgumentParser(
        description="Compare retrieval backends: dense (BGE, Qwen3) vs. sparse (BM25) vs. hybrid (ITR)."
    )
    parser.add_argument(
        "--models", nargs="+",
        choices=list(BACKEND_CONFIGS.keys()),
        default=["bge", "bm25"],
        help="Which backends to evaluate (default: bge bm25).",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Evaluate all backends.",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Write JSON results to this file.",
    )
    args = parser.parse_args()

    if args.all:
        backends = list(BACKEND_CONFIGS.keys())
        # MLX backends only work on Apple Silicon
        if not _IS_MAC:
            mlx_keys = [k for k in backends if "mlx" in k]
            if mlx_keys:
                print(f"Skipping MLX backends (not macOS): {', '.join(mlx_keys)}")
                backends = [k for k in backends if "mlx" not in k]
    else:
        backends = args.models

    # Print detected hardware
    accel = "CUDA" if _HAS_CUDA else ("MPS" if _IS_MAC else "CPU")
    flash = " + flash-attn" if _HAS_FLASH_ATTN else ""
    print(f"Hardware: {accel}{flash}")


    # Load corpus
    instructions_dir = project_root / "pet_sim" / "instructions"
    if not instructions_dir.exists():
        print(f"ERROR: Instructions directory not found: {instructions_dir}")
        sys.exit(1)

    corpus = Corpus.from_directory(str(instructions_dir))
    print(f"Loaded corpus with {len(corpus)} instructions")
    print(f"Backends to evaluate: {', '.join(backends)}")

    results = []
    for key in backends:
        try:
            result = evaluate_backend(key, corpus)
            results.append(result)
        except Exception as e:
            print(f"\n  SKIPPED {BACKEND_CONFIGS[key]['label']}: {e}")

    # --- Standalone ITR (no governance) and Random-k baselines ---
    # These are evaluated without BEAR's governance pipeline for comparison.
    try:
        from itr import ITR, ITRConfig, InstructionFragment
        from itr.core.types import FragmentType
        import tiktoken

        print(f"\n{'='*60}")
        print(f"  ITR standalone (no governance)")
        print(f"{'='*60}")

        enc = tiktoken.get_encoding("cl100k_base")
        itr_config = ITRConfig(
            k_a_instructions=TOP_K,
            top_m_instructions=30,
            token_budget=50000,
            embedding_model="BAAI/bge-base-en-v1.5",
        )
        itr_inst = ITR(itr_config)
        fragments = [
            InstructionFragment(
                id=inst.id,
                content=inst.content,
                token_count=len(enc.encode(inst.content)),
                fragment_type=FragmentType.DOMAIN_SPECIFIC,
                priority=inst.priority,
            )
            for inst in corpus
        ]
        itr_inst.add_instruction_fragments(fragments)

        # Evaluate on all query sets
        itr_sf1, itr_rf1, itr_pf1, itr_nf1, itr_cf1 = [], [], [], [], []
        for q, tags, expected in TEST_QUERIES:
            res = itr_inst.step(q)
            ids = {i.id for i in res.instructions}
            _, _, f = compute_metrics(ids, expected, k=TOP_K)
            itr_sf1.append(f)
            relaxed = expected | RELAXED_EXTRAS.get(q, set())
            _, _, rf = compute_metrics(ids, relaxed, k=TOP_K)
            itr_rf1.append(rf)
        for q, tags, expected in PARAPHRASE_QUERIES:
            res = itr_inst.step(q)
            ids = {i.id for i in res.instructions}
            _, _, f = compute_metrics(ids, expected, k=TOP_K)
            itr_pf1.append(f)
        for q, tags, expected in NO_TAG_QUERIES:
            res = itr_inst.step(q)
            ids = {i.id for i in res.instructions}
            _, _, f = compute_metrics(ids, expected, k=TOP_K)
            itr_nf1.append(f)
        for q, tags, expected in COMPLEX_QUERIES:
            res = itr_inst.step(q)
            ids = {i.id for i in res.instructions}
            _, _, f = compute_metrics(ids, expected, k=TOP_K)
            itr_cf1.append(f)

        arr_isf1 = np.array(itr_sf1)
        arr_irf1 = np.array(itr_rf1)
        arr_ipf1 = np.array(itr_pf1)
        arr_inf1 = np.array(itr_nf1)
        arr_icf1 = np.array(itr_cf1)

        isf1_mean, isf1_lo, isf1_hi = bootstrap_ci(arr_isf1)
        irf1_mean, irf1_lo, irf1_hi = bootstrap_ci(arr_irf1)
        ipf1_mean, ipf1_lo, ipf1_hi = bootstrap_ci(arr_ipf1)
        inf1_mean, inf1_lo, inf1_hi = bootstrap_ci(arr_inf1)
        icf1_mean, icf1_lo, icf1_hi = bootstrap_ci(arr_icf1)

        print(f"  Strict  F1@{TOP_K} = {isf1_mean:.3f}  [{isf1_lo:.3f}, {isf1_hi:.3f}]")
        print(f"  Relaxed F1@{TOP_K} = {irf1_mean:.3f}  [{irf1_lo:.3f}, {irf1_hi:.3f}]")
        print(f"  Para    F1@{TOP_K} = {ipf1_mean:.3f}  [{ipf1_lo:.3f}, {ipf1_hi:.3f}]")
        print(f"  No-tag  F1@{TOP_K} = {inf1_mean:.3f}  [{inf1_lo:.3f}, {inf1_hi:.3f}]")
        print(f"  Complex F1@{TOP_K} = {icf1_mean:.3f}  [{icf1_lo:.3f}, {icf1_hi:.3f}]")

        itr_result = {
            "label": "ITR standalone (no governance)",
            "short": "ITR-standalone",
            "strict_f1": isf1_mean, "strict_f1_ci": (isf1_lo, isf1_hi),
            "relaxed_f1": irf1_mean, "relaxed_f1_ci": (irf1_lo, irf1_hi),
            "para_f1": ipf1_mean, "para_f1_ci": (ipf1_lo, ipf1_hi),
            "notag_f1": inf1_mean, "notag_f1_ci": (inf1_lo, inf1_hi),
            "complex_f1": icf1_mean, "complex_f1_ci": (icf1_lo, icf1_hi),
            "avg_query_ms": 0.0, "p95_query_ms": 0.0,
            "n_queries": len(TEST_QUERIES),
            "_strict_f1_scores": arr_isf1,
            "_relaxed_f1_scores": arr_irf1,
            "_para_f1_scores": arr_ipf1,
            "_notag_f1_scores": arr_inf1,
            "_complex_f1_scores": arr_icf1,
        }
        results.append(itr_result)
    except ImportError:
        print("\n  ITR standalone skipped (instruction-tool-retrieval not installed)")
    except Exception as e:
        print(f"\n  ITR standalone skipped: {e}")

    # --- Random-k baseline ---
    print(f"\n{'='*60}")
    print(f"  Random-k baseline (k={TOP_K}, 1000 trials)")
    print(f"{'='*60}")
    rng = np.random.default_rng(42)
    all_ids = [inst.id for inst in corpus]
    rk_sf1, rk_rf1, rk_pf1, rk_nf1, rk_cf1 = [], [], [], [], []
    for q, tags, expected in TEST_QUERIES:
        trials = [compute_metrics(set(rng.choice(all_ids, size=TOP_K, replace=False)), expected, k=TOP_K)[2] for _ in range(1000)]
        rk_sf1.append(np.mean(trials))
        relaxed = expected | RELAXED_EXTRAS.get(q, set())
        trials_r = [compute_metrics(set(rng.choice(all_ids, size=TOP_K, replace=False)), relaxed, k=TOP_K)[2] for _ in range(1000)]
        rk_rf1.append(np.mean(trials_r))
    for q, tags, expected in PARAPHRASE_QUERIES:
        trials = [compute_metrics(set(rng.choice(all_ids, size=TOP_K, replace=False)), expected, k=TOP_K)[2] for _ in range(1000)]
        rk_pf1.append(np.mean(trials))
    for q, tags, expected in NO_TAG_QUERIES:
        trials = [compute_metrics(set(rng.choice(all_ids, size=TOP_K, replace=False)), expected, k=TOP_K)[2] for _ in range(1000)]
        rk_nf1.append(np.mean(trials))
    for q, tags, expected in COMPLEX_QUERIES:
        trials = [compute_metrics(set(rng.choice(all_ids, size=TOP_K, replace=False)), expected, k=TOP_K)[2] for _ in range(1000)]
        rk_cf1.append(np.mean(trials))

    arr_rksf1 = np.array(rk_sf1)
    arr_rkrf1 = np.array(rk_rf1)
    arr_rkpf1 = np.array(rk_pf1)
    arr_rknf1 = np.array(rk_nf1)
    arr_rkcf1 = np.array(rk_cf1)
    rksf1_mean, rksf1_lo, rksf1_hi = bootstrap_ci(arr_rksf1)
    print(f"  Strict  F1@{TOP_K} = {rksf1_mean:.3f}  [{rksf1_lo:.3f}, {rksf1_hi:.3f}]")

    rk_result = {
        "label": "Random-k", "short": "Random-k",
        "strict_f1": rksf1_mean, "strict_f1_ci": (rksf1_lo, rksf1_hi),
        "relaxed_f1": np.mean(rk_rf1), "relaxed_f1_ci": bootstrap_ci(arr_rkrf1),
        "para_f1": np.mean(rk_pf1), "para_f1_ci": bootstrap_ci(arr_rkpf1),
        "notag_f1": np.mean(rk_nf1), "notag_f1_ci": bootstrap_ci(arr_rknf1),
        "complex_f1": np.mean(rk_cf1), "complex_f1_ci": bootstrap_ci(arr_rkcf1),
        "avg_query_ms": 0.0, "p95_query_ms": 0.0,
        "n_queries": len(TEST_QUERIES),
        "_strict_f1_scores": arr_rksf1,
        "_relaxed_f1_scores": arr_rkrf1,
        "_para_f1_scores": arr_rkpf1,
        "_notag_f1_scores": arr_rknf1,
        "_complex_f1_scores": arr_rkcf1,
    }
    results.append(rk_result)

    if not results:
        print("\nNo backends evaluated successfully.")
        sys.exit(1)

    # Summary table with CIs
    print(f"\n\n{'='*80}")
    print(f"  SUMMARY  ({results[0]['n_queries']} standard queries, "
          f"{len(PARAPHRASE_QUERIES)} paraphrase queries, "
          f"{BOOTSTRAP_ITERS:,} bootstrap iterations)")
    print(f"{'='*80}")

    def _ci_str(mean: float, ci: tuple) -> str:
        return f"{mean:.3f} [{ci[0]:.3f}, {ci[1]:.3f}]"

    print(f"\n  Standard Queries — Strict F1@{TOP_K} (95% CI):")
    for r in results:
        print(f"    {r['short']:<20} {_ci_str(r['strict_f1'], r['strict_f1_ci'])}")

    print(f"\n  Standard Queries — Relaxed F1@{TOP_K} (95% CI):")
    for r in results:
        print(f"    {r['short']:<20} {_ci_str(r['relaxed_f1'], r['relaxed_f1_ci'])}")

    print(f"\n  Paraphrase Queries (minimal tags, n={len(PARAPHRASE_QUERIES)}) — F1@{TOP_K} (95% CI):")
    for r in results:
        ci = r.get("para_f1_ci", (0, 0))
        print(f"    {r['short']:<20} {_ci_str(r.get('para_f1', 0), ci)}")

    print(f"\n  No-Tag Queries (pure retrieval, n={len(NO_TAG_QUERIES)}) — F1@{TOP_K} (95% CI):")
    for r in results:
        ci = r.get("notag_f1_ci", (0, 0))
        print(f"    {r['short']:<20} {_ci_str(r.get('notag_f1', 0), ci)}")

    print(f"\n  Complex Queries (multi-intent/temporal/indirect/adversarial, n={len(COMPLEX_QUERIES)}) — F1@{TOP_K} (95% CI):")
    for r in results:
        ci = r.get("complex_f1_ci", (0, 0))
        print(f"    {r['short']:<20} {_ci_str(r.get('complex_f1', 0), ci)}")

    print(f"\n  Latency:")
    for r in results:
        print(f"    {r['short']:<20} avg={r['avg_query_ms']:.1f}ms  p95={r['p95_query_ms']:.1f}ms")

    # Paired significance tests (all pairs) with effect sizes
    def _sig(p: float) -> str:
        if p < 0.001: return f"{p:.4f}***"
        if p < 0.01: return f"{p:.4f}** "
        if p < 0.05: return f"{p:.4f}*  "
        return f"{p:.4f}   "

    def _cohens_d(a_scores: np.ndarray, b_scores: np.ndarray) -> float:
        """Cohen's d for paired samples."""
        diff = a_scores - b_scores
        sd = np.std(diff, ddof=1)
        return np.mean(diff) / sd if sd > 0 else float('inf')

    if len(results) > 1:
        print(f"\n  Paired Bootstrap Tests (p-values, H0: no difference):")
        print(f"  {'Pair':<40} {'Strict':>10} {'Relaxed':>10} {'Paraph':>10} {'No-tag':>10} {'Complex':>10}")
        print("  " + "-" * 90)
        for i in range(len(results)):
            for j in range(i + 1, len(results)):
                a, b = results[i], results[j]
                pair = f"{a['short']} vs {b['short']}"
                p_strict = paired_bootstrap_test(a["_strict_f1_scores"], b["_strict_f1_scores"])
                p_relax = paired_bootstrap_test(a["_relaxed_f1_scores"], b["_relaxed_f1_scores"])
                p_para = paired_bootstrap_test(a["_para_f1_scores"], b["_para_f1_scores"])
                p_notag = paired_bootstrap_test(a["_notag_f1_scores"], b["_notag_f1_scores"])
                p_complex = paired_bootstrap_test(a["_complex_f1_scores"], b["_complex_f1_scores"])
                print(f"  {pair:<40} {_sig(p_strict):>10} {_sig(p_relax):>10} {_sig(p_para):>10} {_sig(p_notag):>10} {_sig(p_complex):>10}")

        # Effect sizes (Cohen's d) for key pairs
        print(f"\n  Cohen's d Effect Sizes (positive = first backend higher):")
        print(f"  {'Pair':<40} {'Strict':>8} {'Relaxed':>8} {'Paraph':>8} {'No-tag':>8} {'Complex':>8}")
        print("  " + "-" * 80)
        for i in range(len(results)):
            for j in range(i + 1, len(results)):
                a, b = results[i], results[j]
                pair = f"{a['short']} vs {b['short']}"
                d_strict = _cohens_d(a["_strict_f1_scores"], b["_strict_f1_scores"])
                d_relax = _cohens_d(a["_relaxed_f1_scores"], b["_relaxed_f1_scores"])
                d_para = _cohens_d(a["_para_f1_scores"], b["_para_f1_scores"])
                d_notag = _cohens_d(a["_notag_f1_scores"], b["_notag_f1_scores"])
                d_complex = _cohens_d(a["_complex_f1_scores"], b["_complex_f1_scores"])
                print(f"  {pair:<40} {d_strict:>8.3f} {d_relax:>8.3f} {d_para:>8.3f} {d_notag:>8.3f} {d_complex:>8.3f}")

    print_latex_table(results)

    # Save JSON (strip numpy arrays)
    output_path = args.output or str(
        project_root / "results" / "backend_comparison.json"
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    json_results = []
    for r in results:
        jr = {k: v for k, v in r.items() if not k.startswith("_")}
        # Convert tuples to lists for JSON
        for key in ("strict_f1_ci", "relaxed_f1_ci", "para_f1_ci", "notag_f1_ci", "complex_f1_ci"):
            if key in jr and isinstance(jr[key], tuple):
                jr[key] = list(jr[key])
        json_results.append(jr)
    with open(output_path, "w") as f:
        json.dump(json_results, f, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
