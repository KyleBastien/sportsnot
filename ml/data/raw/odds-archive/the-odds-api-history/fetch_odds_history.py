#!/usr/bin/env python3
"""Fetch The Odds API NHL history without placing plaintext inside the repo."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from odds_archive_common import assert_outside_repository, load_env_value
from odds_history_client import Client
from odds_history_models import REGIONS, SEASONS, ApiRequest, ClientSettings, RequestPlan
from odds_history_plans import build_request_plans, print_bulk_estimate
from odds_history_probe import run_probe
from odds_history_tables import build_plaintext_tables, load_historical_payload


@dataclass(frozen=True)
class BulkResult:
    client: Client
    fetched: int
    reused: int
    prior_credits: int


def _bulk_request(plan: RequestPlan, number: int, total: int) -> ApiRequest:
    return ApiRequest(
        label=f"bulk {number}/{total} {plan.season} type={plan.game_type_id}",
        path="/historical/sports/icehockey_nhl/odds",
        params={
            "regions": ",".join(REGIONS),
            "markets": ",".join(plan.markets),
            "date": plan.requested_iso,
            "dateFormat": "iso",
            "oddsFormat": "decimal",
        },
        output_name=(Path(plan.season) / plan.raw_relative_path).as_posix(),
        estimated_cost=plan.estimated_cost,
    )


def _fetch_plans(client: Client, scratch: Path, plans: list[RequestPlan]) -> tuple[int, int]:
    reused = 0
    fetched = 0
    for number, plan in enumerate(plans, start=1):
        raw_path = scratch / plan.season / plan.raw_relative_path
        if raw_path.exists():
            load_historical_payload(raw_path)
            reused += 1
            continue
        client.get(_bulk_request(plan, number, len(plans)))
        fetched += 1
    return fetched, reused


def _write_bulk_manifest(
    scratch: Path,
    plans: list[RequestPlan],
    result: BulkResult,
) -> None:
    manifest = {
        "seasons": list(SEASONS),
        "requests": len(plans),
        "estimated_bulk_credits": sum(plan.estimated_cost for plan in plans),
        "prior_probe_credits": result.prior_credits,
        "fetched_this_run": result.fetched,
        "reused": result.reused,
        "network_credits_this_run": result.client.actual,
        "stats": build_plaintext_tables(scratch, plans),
    }
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    (scratch / "_bulk-manifest.json").write_text(text, encoding="utf-8")
    print(text, end="", flush=True)


def run_bulk(args: argparse.Namespace) -> None:
    scratch = args.scratch.resolve()
    assert_outside_repository(scratch)
    archive = Path(__file__).resolve().parents[2] / "nhl-archive"
    plans = build_request_plans(archive)
    print_bulk_estimate(plans, args.prior_credits, args.max_credits)
    scratch.mkdir(parents=True, exist_ok=True)
    client = Client(
        ClientSettings(
            api_key=load_env_value("ODDS_API_KEY"),
            scratch=scratch,
            max_credits=args.max_credits - args.prior_credits,
            request_log=scratch / "_request-log.jsonl",
            progress_every=args.progress_every,
            delay=args.delay,
        )
    )
    fetched, reused = _fetch_plans(client, scratch, plans)
    result = BulkResult(client, fetched, reused, args.prior_credits)
    _write_bulk_manifest(scratch, plans, result)


def _run_probe(args: argparse.Namespace) -> None:
    scratch = args.scratch.resolve()
    assert_outside_repository(scratch)
    settings = ClientSettings(
        api_key=load_env_value("ODDS_API_KEY"),
        scratch=scratch,
        max_credits=args.max_credits,
    )
    run_probe(Client(settings), scratch, args.max_credits)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    probe = subparsers.add_parser("probe")
    probe.add_argument(
        "--scratch",
        type=Path,
        default=Path(tempfile.gettempdir()) / "odds-history",
    )
    probe.add_argument("--max-credits", type=int, default=300)
    bulk = subparsers.add_parser("bulk")
    bulk.add_argument(
        "--scratch",
        type=Path,
        default=Path(tempfile.gettempdir()) / "odds-history",
    )
    bulk.add_argument("--max-credits", type=int, default=90_000)
    bulk.add_argument("--prior-credits", type=int, default=0)
    bulk.add_argument("--progress-every", type=int, default=25)
    bulk.add_argument("--delay", type=float, default=0.2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "probe":
            _run_probe(args)
        elif args.command == "bulk":
            run_bulk(args)
        else:
            raise RuntimeError(f"unsupported command: {args.command}")
        return 0
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
