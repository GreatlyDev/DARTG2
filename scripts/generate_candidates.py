import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.generation import (
    OpenAIResponsesClient,
    existing_candidate_ids,
    generate_candidate_record,
    load_env_file,
    sleep_between_calls,
)
from dart_pipeline.io_utils import read_records, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate DART candidate variants from rendered prompt jobs.")
    parser.add_argument("--jobs", required=True, type=Path, help="Input prompt jobs JSONL.")
    parser.add_argument("--output", required=True, type=Path, help="Output generated candidates JSONL.")
    parser.add_argument("--model", default="gpt-5.2", help="OpenAI model to use.")
    parser.add_argument("--env-file", default=Path(".env"), type=Path, help="Optional .env file containing OPENAI_API_KEY.")
    parser.add_argument("--limit", type=int, default=None, help="Only generate the first N remaining jobs.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between API calls.")
    parser.add_argument("--timeout", type=int, default=120, help="HTTP timeout per API call in seconds.")
    parser.add_argument("--max-output-tokens", type=int, default=900, help="Maximum output tokens per candidate.")
    parser.add_argument("--status", default="demo_unvalidated", help="Generation status label to store with each candidate.")
    parser.add_argument("--resume", action="store_true", help="Skip candidate IDs already present in the output file.")
    parser.add_argument("--print-output", action="store_true", help="Print each generated candidate response to the terminal.")
    args = parser.parse_args()

    load_env_file(args.env_file)
    import os

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set. Put it in your environment or pass --env-file .env.")

    jobs = read_records(args.jobs)
    existing_rows = read_records(args.output) if args.output.exists() and args.resume else []
    seen = existing_candidate_ids(existing_rows)
    remaining_jobs = [job for job in jobs if str(job.get("job_id")) not in seen]
    if args.limit is not None:
        remaining_jobs = remaining_jobs[: args.limit]

    client = OpenAIResponsesClient(
        api_key=api_key,
        model=args.model,
        timeout=args.timeout,
        max_output_tokens=args.max_output_tokens,
    )

    generated_rows = list(existing_rows)
    total = len(remaining_jobs)
    for index, job in enumerate(remaining_jobs, start=1):
        print(f"[{index}/{total}] Generating {job.get('job_id')}")
        record = generate_candidate_record(job, client, generation_status=args.status)
        generated_rows.append(record)
        write_jsonl(args.output, generated_rows)
        if args.print_output:
            print("")
            print(f"Candidate ID: {record['candidate_id']}")
            print(f"Dialect: {record['dialect_family']}")
            print("Candidate response:")
            print(record["candidate_response"])
            print("-" * 80)
        sleep_between_calls(args.sleep)

    print(f"Wrote {len(generated_rows)} candidate records to {args.output}")


if __name__ == "__main__":
    main()
