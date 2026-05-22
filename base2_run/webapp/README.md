# base2 sweep viewer

FastAPI single-page UI that loads
`base2_run/output/base2__claude-sonnet-4-6__all.jsonl` and exposes per-record
diff views, family stats, prompt/inventory introspection, and CSV/JSONL
download of any filtered subset.

The server itself has no API-key requirement — it only reads the JSONL file on
disk. (API keys are only needed if you re-run the generator,
`base2_run/run_base2.py`.)

## Dependencies

Only three third-party packages:

- `fastapi` — HTTP framework and routing
- `uvicorn[standard]` — ASGI server (with websockets / reload support)
- `jinja2` — template rendering for the index page

Everything else (`difflib`, `hashlib`, `csv`, `json`, `pathlib`, …) is stdlib.

Pinned in `requirements.txt`.

## Setup with uv

```sh
# 1. From repo root (or anywhere — uv handles the path):
cd base2_run/webapp

# 2. Create a venv and install:
uv venv
uv pip install -r requirements.txt

# 3. Run the server (binds 127.0.0.1:8765):
uv run python server.py
```

Then open <http://127.0.0.1:8765>.

### One-shot alternative (no persistent venv)

```sh
cd base2_run/webapp
uv run --with-requirements requirements.txt python server.py
```

This builds an ephemeral environment, runs the server, and discards the
environment when you Ctrl-C. Useful for quick checks without committing a
`.venv/` directory.

### Dev mode (auto-reload on edits)

```sh
cd base2_run
uv run --with-requirements webapp/requirements.txt \
    uvicorn webapp.server:app --reload --host 127.0.0.1 --port 8765
```

`--reload` watches `server.py`, the templates, and the static files; restart
is automatic on save.

## Pointing at a different dataset

`server.py` reads `DEFAULT_DATASET = base2_run/output/base2__claude-sonnet-4-6__all.jsonl`.
To load a different JSONL file, edit `DEFAULT_DATASET` near the top of
`server.py` or call `reload_dataset(Path("/abs/path/to/file.jsonl"))` from a
Python REPL after importing the module.

## Sanity check

```sh
curl -s http://127.0.0.1:8765/healthz
# → "ok · N records loaded from base2__claude-sonnet-4-6__all.jsonl"
```

If `N` is zero, the dataset path is wrong or the file is empty.

## Files

```
base2_run/webapp/
├── README.md              (this file)
├── requirements.txt       (three pinned deps)
├── server.py              (FastAPI app — entrypoint)
├── static/
│   ├── app.css
│   └── app.js
└── templates/
    └── index.html
```
