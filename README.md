# Hotelli Frami Voice Assistant

FastAPI service for Twilio voice calls, OpenAI Realtime handling, availability lookups, prompt administration, and privacy-reduced call logging.

## What is ready for GitHub/container handoff

- Runtime dependencies are pinned in `requirements.txt`.
- Secrets stay out of the repo through `.gitignore` and `.dockerignore`.
- The app uses `PUBLIC_BASE_URL` for deployed webhook callbacks.
- Container-friendly storage can be configured with `APP_DATA_DIR`.
- A `/healthz` endpoint is available for container health checks.
- Strict dependency validation at startup is configurable with `VALIDATE_STARTUP_DEPENDENCIES`.

## Required runtime environment

These are required for the live Twilio/OpenAI voice flow:

- `OPENAI_API_KEY`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_PHONE_NUMBER`
- `PUBLIC_BASE_URL`

`OPENAI_REALTIME_MODEL` can be switched between current Realtime model families such as `gpt-realtime` and `gpt-realtime-2`. The app uses the current nested Realtime session schema for both, only sends `reasoning.effort` for the `gpt-realtime-2` family, and omits `session.temperature` for the `gpt-realtime*` family because the live API rejects that field there.

When `OPENAI_API_PROVIDER=azure-openai`, replace `OPENAI_API_KEY` with:

- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_REALTIME_DEPLOYMENT`

Optional Azure Realtime overrides:

- `AZURE_OPENAI_REALTIME_API_VERSION`
- `AZURE_OPENAI_REALTIME_URL`
- `AZURE_OPENAI_CHAT_API_VERSION`

The app now supports both current Azure Realtime URL styles:

- GA: `/openai/v1/realtime?model=<deployment>`
- Preview: `/openai/realtime?api-version=<version>&deployment=<deployment>`

If Azure gives you an explicit Realtime websocket URL, set `AZURE_OPENAI_REALTIME_URL` and the app will use it as-is.

For Azure chat-completions side features such as post-call anonymized summaries, the app defaults
to `AZURE_OPENAI_CHAT_API_VERSION=2024-12-01-preview`. This matters for reasoning deployments such
as `o4-mini`, which Azure rejects on older chat API versions.

`PUBLIC_BASE_URL` must be the externally reachable HTTPS base URL for this service, for example `https://voice.example.com`. If the app is published behind a reverse proxy under a path prefix, include that full prefix in the URL, for example `https://demo.example.com/hotelli-frami`.

When deploying behind a reverse proxy path prefix:

- The proxy must forward WebSocket connections for `/media-stream`.
- The app now supports either stripped-prefix forwarding or preserved-prefix forwarding, as long as `PUBLIC_BASE_URL` includes the public path prefix.

The inbound Twilio call flow now plays an AI disclosure before connecting the caller to the realtime media stream. This is enabled by default and can be configured with:

- `TWILIO_AI_DISCLOSURE_ENABLED`
- `TWILIO_AI_DISCLOSURE_MESSAGE_FI`
- `TWILIO_AI_DISCLOSURE_MESSAGE_EN`

Start from [.env.example](.env.example) and create a real `.env` outside Git history.

## Recommended container settings

- Set `APP_DATA_DIR=/data`
- Mount `/data` as a persistent volume
- Keep `VALIDATE_STARTUP_DEPENDENCIES=false` for generic health/startup checks, or set it to `true` if you want the container to fail fast when live credentials are missing

The app writes prompt history, privacy-reduced session logs, daily summary history, and feedback survey history under `APP_DATA_DIR` unless those paths are overridden individually.

If `DAILY_SUMMARY_TO_PHONE` is set, the app also runs an in-process daily SMS digest scheduler inside the container. By default it sends the last 24 hours of activity every day at `08:00` in `DAILY_SUMMARY_TIMEZONE` (default `Europe/Helsinki`). You can disable it with `DAILY_SUMMARY_AUTO_SEND_ENABLED=false` or change the send time with `DAILY_SUMMARY_SEND_TIME=HH:MM`.

## Build and run

```bash
docker build -t hotelli-frami-voice .
docker run --rm -p 8000:8000 --env-file .env -e APP_DATA_DIR=/data -v hotelli-frami-data:/data hotelli-frami-voice
```

Health check endpoint:

```text
GET /healthz
```

## Local verification

Run tests with:

```bash
python -m unittest discover -s tests
```

Run the app locally with:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

If startup fails with a missing `python-multipart` error, reinstall dependencies with `pip install -r requirements.txt` or rebuild the Docker image so the runtime matches `requirements.txt`.
