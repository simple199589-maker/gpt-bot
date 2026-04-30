# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development commands

- Install dependencies: `uv sync`
- Run the API locally: `uv run .\main.py serve --config .\config.json`
- Run the default foreground service mode: `uv run .\main.py --config .\config.json`
- Perform the first interactive Telegram login: `uv run .\main.py login --config .\config.json`
- Run without interactive login prompts, for daemon/Docker-style startup: `uv run .\main.py serve --config .\config.json --non-interactive`
- Start/inspect/stop the Windows-style daemon:
  - `uv run .\main.py daemon start --config .\config.json`
  - `uv run .\main.py daemon status --config .\config.json`
  - `uv run .\main.py daemon stop --config .\config.json`
- Run all tests: `uv run python -m unittest discover -s tests`
- Run a single test file: `uv run python -m unittest tests.test_workflow_service`
- Run a single test case: `uv run python -m unittest tests.test_workflow_service.ActivationClassificationTests.test_activation_queue_full_message_returns_queue_full_status`
- Build Docker image: `docker build -t gpt-bot .`
- Run with Docker Compose: `docker compose up -d`; view logs with `docker compose logs -f gpt-bot`

The project requires Python 3.13+. Runtime configuration is copied from `config.example.json` to `config.json`; `GPT_BOT_API_KEY` can supply `api.api_key` when that field is blank.

## Architecture overview

This is a FastAPI wrapper around a Telegram user-account session. It automates menu interactions with a target Telegram bot through Telethon and exposes those workflows as HTTP endpoints.

- `main.py` is the CLI entry point. It parses `serve`, `login`, and `daemon` commands, loads config, validates API runtime settings, and starts Uvicorn or the daemon manager.
- `app_config.py` owns default config merging, runtime validation, proxy conversion, daemon path resolution, and normalized keyword matching. Workflow buttons, prompts, timeout values, and result keyword groups are config-driven.
- `telegram_service.py` wraps Telethon. It owns the Telegram client lifecycle, resolves the configured bot, listens for incoming new/edited messages, stores them in a cursor-addressed event buffer, clicks matching buttons when possible, and falls back to sending text.
- `workflow_service.py` translates bot conversations into business operations: Plus activation, Team activation, balance/progress query, and card-code redeem. It waits for configured prompts, sends user inputs, classifies progress/terminal messages, and returns `WorkflowResult` objects.
- `job_queue.py` serializes all Telegram workflows through one worker coroutine. This is central to the design: concurrent HTTP requests must not interleave Telegram conversations. Jobs keep `request_id`, queue position, state, first response, final result, and activation menu-restore flags.
- `api_server.py` builds the FastAPI app and owns request/response behavior. It wires service lifespan, API-key verification, the workflow queue, scheduled redeem startup, and endpoints under `/api/v1/*`. Activation endpoints can return as soon as a progress message is seen; callers then poll `GET /api/v1/requests/{request_id}` for the terminal result.
- `scheduled_redeem.py` optionally submits redeem jobs at configured local daily `HH:MM` times and reuses the same serial queue as manual API calls.
- `daemon_manager.py` starts/stops/status-checks a detached local service process using configured `.runtime` PID/log paths.
- `schemas.py` defines Pydantic request and response models, using camelCase aliases for the public API.

## API behavior notes

- All business endpoints require `X-API-Key` or `Authorization: Bearer ...`; `GET /healthz` is unauthenticated.
- Queue fullness is enforced by `api.queue_max_size` and returns HTTP 429.
- Activation workflows (`activate_plus`, `activate_team`) are long-running: a `processing`, `queued`, or `already_queued` response is not final success. The final decision comes from `GET /api/v1/requests/{request_id}`.
- When an activation job reaches a terminal state, the first status poll claims a one-time menu restore and sends the configured `workflow.back_text`.
- Balance and redeem endpoints wait for their final workflow result before responding; redeem always attempts to return to the main menu in a `finally` path.

## Testing guidance

Tests are `unittest` based and currently focus on pure classification/response behavior without connecting to Telegram. Prefer adding tests around `workflow_service.py` classifiers and `api_server.py` response builders when changing public API semantics or bot-message classification.

Avoid running service commands against a real Telegram session unless the task requires integration verification and a valid local `config.json`/`.session` is available.
