import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_step(args: list[str]) -> None:
    print("")
    print("$ " + " ".join(args))
    subprocess.run(args, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the final-80 base/gpt-4o DART candidate workflow.")
    parser.add_argument("--anchors", type=Path, default=Path("data/raw/DART_FINAL_80_ANCHORS.csv"))
    parser.add_argument("--features", type=Path, default=Path("config/features.index.json"))
    parser.add_argument("--candidates", type=int, default=3)
    parser.add_argument("--model", default="gpt-4o")
    parser.add_argument("--skip-generation", action="store_true", help="Use existing generated candidates and run checks only.")
    parser.add_argument("--limit", type=int, default=None, help="Optional generation limit for smoke tests.")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    assignments = Path("data/assignments/final80_base_gpt4o_assignments.jsonl")
    jobs = Path("data/generated/final80_base_gpt4o_prompt_jobs.jsonl")
    raw = Path("data/generated/final80_base_gpt4o_candidates_raw.jsonl")
    prefiltered = Path("data/generated/final80_base_gpt4o_candidates_prefiltered.jsonl")
    scored = Path("data/generated/final80_base_gpt4o_candidates_scored.jsonl")
    curated = Path("data/generated/final80_base_gpt4o_candidates_curated.jsonl")
    rejected = Path("data/generated/final80_base_gpt4o_candidates_rejected.jsonl")
    report = Path("docs/final80_base_gpt4o_candidates_review.md")

    run_step([
        sys.executable,
        "scripts/build_assignments.py",
        "--anchors",
        str(args.anchors),
        "--features",
        str(args.features),
        "--strategy",
        "greedy",
        "--candidates",
        str(args.candidates),
        "--output",
        str(assignments),
    ])
    run_step([
        sys.executable,
        "scripts/render_prompt_jobs.py",
        "--anchors",
        str(args.anchors),
        "--assignments",
        str(assignments),
        "--features",
        str(args.features),
        "--template",
        "prompts/generation_v1.txt",
        "--output",
        str(jobs),
    ])
    if not args.skip_generation:
        generation_cmd = [
            sys.executable,
            "scripts/generate_candidates.py",
            "--jobs",
            str(jobs),
            "--output",
            str(raw),
            "--model",
            args.model,
            "--status",
            "demo_unvalidated",
            "--retry-failures",
            "--resume",
        ]
        if args.limit is not None:
            generation_cmd.extend(["--limit", str(args.limit)])
        elif args.resume:
            generation_cmd.append("--resume")
        run_step(generation_cmd)
    run_step([
        sys.executable,
        "scripts/prefilter_candidates.py",
        "--anchors",
        str(args.anchors),
        "--candidates",
        str(raw),
        "--features",
        str(args.features),
        "--output",
        str(prefiltered),
    ])
    run_step([
        sys.executable,
        "scripts/score_candidates.py",
        "--candidates",
        str(prefiltered),
        "--features",
        str(args.features),
        "--output",
        str(scored),
    ])
    run_step([
        sys.executable,
        "scripts/curate_candidates.py",
        "--candidates",
        str(scored),
        "--output",
        str(curated),
        "--rejections-output",
        str(rejected),
    ])
    run_step([
        sys.executable,
        "scripts/render_candidate_report.py",
        "--anchors",
        str(args.anchors),
        "--candidates",
        str(scored),
        "--output",
        str(report),
    ])
    print("")
    print(f"Workflow outputs:")
    print(f"  Raw candidates: {raw}")
    print(f"  Scored candidates: {scored}")
    print(f"  Curated passing candidates: {curated}")
    print(f"  Rejected candidates: {rejected}")
    print(f"  Review report: {report}")


if __name__ == "__main__":
    main()
