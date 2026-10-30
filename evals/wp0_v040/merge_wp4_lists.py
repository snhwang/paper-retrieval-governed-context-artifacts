"""Gather the k=50 lists that different lanes wrote into one folder for WP4.

    python merge_wp4_lists.py --out DIR SRC_DIR [SRC_DIR ...]

Each SRC_DIR holds toolbench/ and metatool-tags/ (dump_toolbench_lists.py
output). The lists are copied as they are. meta.json must agree on the corpus
order and the queries across sources (the script stops otherwise), and the
merged meta.json keeps every source's _provenance under _provenance_sources.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("src", nargs="+")
    a = ap.parse_args()
    out = Path(a.out)
    for bench in ("toolbench", "metatool-tags"):
        merged, provs = None, []
        (out / bench).mkdir(parents=True, exist_ok=True)
        for s in a.src:
            d = Path(s) / bench
            if not (d / "meta.json").exists():
                continue
            m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
            prov = m.pop("_provenance", None)
            if merged is None:
                merged = m
            elif m != merged:
                raise SystemExit(f"{d}/meta.json disagrees with the first source (corpus or queries)")
            provs.append({"source": str(d), "provenance": prov})
            for f in sorted(d.iterdir()):
                if f.name == "meta.json" or f.suffix not in (".npz", ".json"):
                    continue
                dst = out / bench / f.name
                if dst.exists() and dst.read_bytes() != f.read_bytes():
                    raise SystemExit(f"{dst} exists with other content")
                shutil.copy2(f, dst)
                print(f"{bench}: {f.name} <- {d}")
        if merged is None:
            continue
        merged["_provenance_sources"] = provs
        (out / bench / "meta.json").write_text(json.dumps(merged), encoding="utf-8")


if __name__ == "__main__":
    main()
