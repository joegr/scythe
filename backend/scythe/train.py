"""Train a spaCy span categorizer from the labeled spans in the database.

    python -m scythe.train [--spans-key sc] [--max-steps 2000] [--max-size 0]

Writes ./models/<timestamp>/{config.cfg, train.spacy, dev.spacy, model-best/, scythe.json}.
The newest directory with a `model-best` is what `/api/cards/{id}/suggest` uses.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from confection import Config
from spacy.cli.init_config import init_config

from .config import settings
from .db import SessionLocal
from .spacy_io import ExportFilter, split_docbins

GOLD_SOURCES = ["manual", "import"]  # ner/model spans are never treated as gold unless accepted->manual


def spancat_config(spans_key: str = "sc", max_size: int = 12, max_steps: int = 2000) -> Config:
    """Stock `spacy init config -p spancat -o efficiency`, with an n-gram range suggester sized for
    debate spans (underlines are phrases, not 1-3 grams) and score weights matching `spans_key`."""
    cfg = init_config(lang="en", pipeline=["spancat"], optimize="efficiency")
    cat = cfg["components"]["spancat"]
    cat["spans_key"] = spans_key
    cat["suggester"] = {"@misc": "spacy.ngram_range_suggester.v1", "min_size": 1, "max_size": max_size}
    cfg["training"]["score_weights"] = {
        f"spans_{spans_key}_f": 1.0, f"spans_{spans_key}_p": 0.0, f"spans_{spans_key}_r": 0.0,
    }
    cfg["training"]["max_steps"] = max_steps
    cfg["training"]["patience"] = max(200, max_steps // 4)
    cfg["corpora"]["train"]["max_length"] = 0
    return cfg


def suggested_max_size(docs_bin, vocab, cap: int = 24) -> int:
    lengths = sorted(len(sp) for doc in docs_bin.get_docs(vocab) for group in doc.spans.values() for sp in group)
    if not lengths:
        return 8
    return max(3, min(cap, lengths[int(0.95 * (len(lengths) - 1))]))


def main(argv: list[str] | None = None) -> Path:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--spans-key", default="sc")
    p.add_argument("--labels", nargs="*", help="restrict to these label names")
    p.add_argument("--max-steps", type=int, default=2000)
    p.add_argument("--max-size", type=int, default=0, help="longest span (tokens) to suggest; 0 = auto (p95)")
    p.add_argument("--output", type=Path, default=None)
    args = p.parse_args(argv)

    import spacy
    from spacy.cli.train import train

    out = args.output or settings.models_dir / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    f = ExportFilter(spans_keys=[args.spans_key], labels=args.labels or None, sources=GOLD_SOURCES, accepted_only=True)
    with SessionLocal() as session:
        train_db, dev_db, n_train, n_dev = split_docbins(session, f)
    if n_train == 0:
        sys.exit("no labeled cards to train on")
    train_db.to_disk(out / "train.spacy")
    dev_db.to_disk(out / "dev.spacy")
    max_size = args.max_size or suggested_max_size(train_db, spacy.blank("en").vocab)
    spancat_config(args.spans_key, max_size, args.max_steps).to_disk(out / "config.cfg")
    meta = dict(spans_key=args.spans_key, n_train=n_train, n_dev=n_dev, max_size=max_size, labels=args.labels,
                started=datetime.now().isoformat(), status="training")
    (out / "scythe.json").write_text(json.dumps(meta, indent=2))
    print(f"training on {n_train} docs, dev {n_dev}, max span size {max_size} -> {out}", flush=True)
    try:
        train(out / "config.cfg", out, overrides={"paths.train": str(out / "train.spacy"),
                                                  "paths.dev": str(out / "dev.spacy")})
        meta["status"] = "done"
    except BaseException:
        meta["status"] = "failed"
        raise
    finally:
        meta["finished"] = datetime.now().isoformat()
        (out / "scythe.json").write_text(json.dumps(meta, indent=2))
    return out


if __name__ == "__main__":
    main()
