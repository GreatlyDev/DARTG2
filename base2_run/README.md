# base2_run — DART dialect-rewrite sweep + viewer

Self-contained bundle of the base2 strategy: the JSONL data, the prompt and
inventory files, the generator pipeline (`run_base2.py`), and a FastAPI
single-page viewer (`webapp/`).

## Contents

```
base2_run/
├── README.md              (this file)
├── run_base2.py           generator entrypoint
├── lib/                   pipeline modules
├── prompts/base2.md       prompt template
├── config/features/*.json per-family dialect inventories
├── data/                  80 anchor essays (DART_FINAL_80_ANCHORS.csv)
├── output/                produced JSONL files (the viewer reads these)
│   ├── base2__claude-sonnet-4-6__all.jsonl
│   └── base2__gpt-5.2__all.jsonl
└── webapp/                FastAPI viewer
    ├── server.py
    ├── requirements.txt
    ├── README.md
    ├── static/
    └── templates/
```

The viewer needs **no API keys**, only the JSONL files in `output/`. The
generator (`run_base2.py`) is what needs API keys.

---

## Quick start — viewer only

```sh
# 1. Unzip
unzip base2_run.zip
cd base2_run/webapp

# 2. Install (one-time)
uv venv
uv pip install -r requirements.txt

# 3. Run
uv run python server.py
```

Open <http://127.0.0.1:8765>.

The sidebar dropdown lists every `*.jsonl` in `base2_run/output/`; pick one and
the dashboard / table / reader / prompts tabs reload onto that dataset
without restarting the server.

### No `uv`?

Plain Python works the same way:

```sh
cd base2_run/webapp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

### Useful viewer flags

```sh
# Pick a non-default startup dataset
python server.py --dataset ../output/base2__gpt-5.2__all.jsonl

# Different port
python server.py --port 8080

# Dev mode (auto-reload on edits)
python server.py --reload

# Sanity check
curl http://127.0.0.1:8765/healthz
# → ok · N records loaded from <file>.jsonl
```

### Stop the server

```sh
kill $(lsof -ti :8765)        # macOS / Linux
```

---

## Running the generator (`run_base2.py`)

Needed only if you want to produce new JSONL output.

### Set up API keys

The generator looks for keys in either:

- the shell environment (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`), or
- key files passed via CLI flags (`--openai-key-file`, `--anthropic-key-file`),
  or
- an `.env` file at the path given by `--env-file` (defaults to the parent
  of `base2_run/`).

Easiest setup inside a standalone `base2_run/` copy:

```sh
cat > .env <<'EOF'
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
EOF
```

Then run with `--env-file ./.env` so the loader looks in `base2_run/` instead
of the parent directory.

### Generator deps

The generator's only non-stdlib runtime dep is `sentence-transformers`
(for the HF cosine pass). You can skip it with `--no-embed`.

```sh
# Optional: install sentence-transformers in a venv at the base2_run root
uv venv
uv pip install sentence-transformers
```

### Commands

```sh
cd base2_run
# Default model is claude-sonnet-4-6
python3 run_base2.py --smoketest --env-file ./.env

# Full 480-record sweep against gpt-5.2 at medium reasoning
python3 run_base2.py --all --env-file ./.env \
    --model gpt-5.2 --reasoning-effort medium

# Cheaper subset
python3 run_base2.py --sample 20 --env-file ./.env --model claude-haiku-4-5
```

Output lands at `output/base2__<model>__all.jsonl` (single combined file) or
`output/base2__<model>__<family>.jsonl` if you pass `--output-split`.

### Supported models

Curated set documented in `run_base2.py`:

- `claude-sonnet-4-6` (default)
- `claude-haiku-4-5`
- `gpt-4o`
- `gpt-4o-mini`
- `gpt-5.2` — supports `--reasoning-effort {minimal,low,medium,high}`

Any other id is dispatched by prefix (`claude-*` → Anthropic, else OpenAI).

**Pricing note:** `lib/pricing.py` still has the `gpt-5.2` row at
`{"in": 0.00, "out": 0.00}` as a placeholder. The script runs fine; cost
totals just report `$0.00`. Update those numbers before relying on the cost
column.

---

## Troubleshooting

**Port already in use.** Another process is bound to 8765:

```sh
lsof -i :8765                  # see what owns it
kill $(lsof -ti :8765)         # kill it, or use --port 8080
```

**Dropdown is empty.** The viewer scans `base2_run/output/`. Check that
`*.jsonl` files exist there.

**`/healthz` says 0 records.** The default startup dataset
(`base2__claude-sonnet-4-6__all.jsonl`) is missing. Either restore it, or
launch with `--dataset path/to/some.jsonl`.

**Module import errors when running `server.py` directly.** The script adds
`base2_run/` to `sys.path` automatically; if you've moved files around, run
it from `base2_run/webapp/` so the relative imports resolve.
