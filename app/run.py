from __future__ import annotations

import argparse

from loguru import logger

from app.config import MAX_WORKERS, ensure_dirs
from app.http_client import setup_logging
from app.stage1_list import run_stage1
from app.stage2_pdf_url import run_stage2
from app.stage3_download import run_stage3
from app.stage4_extract_text import run_stage4
from app.stage5_benchmark import run_stage5
from app.stage6_output import run_stage6


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Nomura Asset Management benchmark extraction pipeline",
    )
    parser.add_argument(
        "--stage",
        choices=["all", "1", "2", "3", "4", "5", "6"],
        default="all",
        help="Stage to run (default: all)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore caches and reprocess",
    )
    parser.add_argument(
        "--max-funds",
        type=int,
        default=None,
        help="Limit number of funds in stage1",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM extraction in stage5",
    )
    parser.add_argument(
        "--llm-provider",
        choices=["auto", "anthropic", "gemini", "openai", "ollama"],
        default="auto",
        help="Select LLM provider (default: auto)",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default=None,
        help="Override LLM model name",
    )
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="Disable OCR fallback in stage4",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=MAX_WORKERS,
        help="Number of concurrent workers (default: 5)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_dirs()
    setup_logging()

    max_funds = args.max_funds if args.max_funds is not None else 100
    use_llm = not args.no_llm
    allow_ocr = not args.no_ocr
    workers = args.workers
    provider = None if args.llm_provider == "auto" else args.llm_provider
    model = args.llm_model

    if args.stage == "all":
        logger.info("Running full pipeline (workers={}, llm_provider={})", workers, args.llm_provider)
        run_stage1(force=args.force, max_funds=max_funds)
        run_stage2(force=args.force, max_workers=workers)
        run_stage3(force=args.force, max_workers=workers)
        run_stage4(force=args.force, allow_ocr=allow_ocr, max_workers=workers)
        records = run_stage5(use_llm=use_llm, provider=provider, model=model)
        run_stage6(records)
        logger.info("Pipeline completed successfully")
        return

    if args.stage == "1":
        run_stage1(force=args.force, max_funds=max_funds)
    elif args.stage == "2":
        run_stage2(force=args.force, max_workers=workers)
    elif args.stage == "3":
        run_stage3(force=args.force, max_workers=workers)
    elif args.stage == "4":
        run_stage4(force=args.force, allow_ocr=allow_ocr, max_workers=workers)
    elif args.stage == "5":
        run_stage5(use_llm=use_llm, provider=provider, model=model)
    elif args.stage == "6":
        run_stage6()
    logger.info("Stage {} completed", args.stage)


if __name__ == "__main__":
    main()

