<!-- GSD:project-start source:PROJECT.md -->

## Project

**Hotelli Frami: Public Voice Agent Demo**

A public demonstration of an AI voice-agent phone-reservation system, built around a
fictional hotel — "Hotelli Frami." A visitor reads the fictional hotel's info on a public
website, calls a real phone number, and watches in real time as an AI voice agent
understands their request and completes a reservation. Hotelli Frami, its address, its
rooms, and every guest-facing detail are fictional; the booking backend is a synthetic,
self-contained demo store with no path to any live production booking system.

**Core Value:** A visitor with no credentials or setup can call the number and watch, in real time, a
genuine AI voice agent understand them and land a reservation — proving the capability
actually works, not just describing it.

### Constraints

- **Standalone demo**: All visitor-facing content (hotel identity, address, rooms, policies) is fictional and self-contained — Why: this is a public showcase, not tied to any real business.
- **Privacy**: Zero real identifiers, addresses, PII, or secrets anywhere in the repo's working tree or history — Why: the repo is public and permanent.
- **Synthetic booking backend**: The demo's availability/reservation store is synthetic and isolated; no code path reaches any live production booking system — Why: public demo traffic must never touch a real, external booking calendar.
- **Cost/abuse exposure**: A public phone number wired to paid Realtime API + Twilio usage, plus live public transcript rendering, needs rate-limiting and a spend ceiling — Why: unmetered public exposure risks runaway cost, spam, and inappropriate content rendering live to anonymous visitors.
- **Tech stack**: Built on FastAPI + Twilio + OpenAI Realtime — Why: a proven, working telephony and voice-agent stack for this kind of live demo.

<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->

## Technology Stack

## Languages

- Python 3.13 - Entire application codebase

## Runtime

- Python 3.13-slim (Docker base image)
- Uvicorn 0.44.0 (ASGI application server)
- pip (Python package manager)
- Lockfile: `requirements.txt` (present with pinned versions)

## Frameworks

- FastAPI 0.136.0 - Web framework for API endpoints and WebSocket handling
- WebSockets 16.0 - WebSocket protocol support for media streaming with OpenAI Realtime API
- asyncio - Standard Python async/await runtime

## Key Dependencies

- fastapi==0.136.0 - REST API and WebSocket routing framework
- uvicorn[standard]==0.44.0 - ASGI server with WebSocket and HTTP/2 support
- websockets==16.0 - Low-level WebSocket client/server implementation for media-stream connections
- twilio==9.10.5 - Twilio SDK for voice calls and SMS (phone number validation, TwiML generation, call management)
- python-dotenv==1.2.2 - Environment variable loading from `.env` files
- python-multipart==0.0.20 - Form data parsing for Twilio webhook payloads

## Configuration

- `python-dotenv` loads configuration from `.env` file at startup (`app/config/settings.py:15`)
- Settings class: `app.config.settings.Settings` - uses `@dataclass(frozen=True)` for immutable configuration
- Configuration sources: environment variables only (no config files required beyond `.env`)
- OpenAI provider selection: `OPENAI_API_PROVIDER` (openai or azure-openai)
- Twilio credentials: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`
- OpenAI credentials: `OPENAI_API_KEY` or Azure equivalents
- Deployment: `PUBLIC_BASE_URL` for webhook callbacks and media stream URLs
- Storage: `APP_DATA_DIR` (default `/data`) for persistent data
- `Dockerfile` - Multi-stage build with Python 3.13-slim
- `compose.yaml` - Docker Compose configuration with volume mounting for persistence

## Platform Requirements

- Python 3.13+
- pip package manager
- Docker (for containerized deployment)
- Docker container (Python 3.13-slim)
- Port 8000 (HTTP/HTTPS and WebSocket)
- Persistent volume at `/data` for state storage
- Environment variables configured via `.env` file
- Health check endpoint: `GET /healthz` (HTTP status check at `http://127.0.0.1:8000/healthz`)

## Architecture Patterns

- Single FastAPI application instance running in Uvicorn
- Path prefix support via `PublicPathPrefixMiddleware` (`app/main.py:22-39`)
- Lifespan management with `@asynccontextmanager` for startup/shutdown tasks
- Single-threaded async event loop with `asyncio`
- Thread pool executor for blocking operations: BookingOnline HTTP requests, OpenAI chat completions for anonymization
- Thread-safe file I/O with `threading.Lock` in `PromptStore` (`app/services/prompt_store.py:51`)

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

## Naming Patterns

- Modules use `snake_case`: `sms_utils.py`, `availability_checker.py`, `conversation_anonymizer.py`
- Test files follow pattern: `test_<module_name>.py` (e.g., `test_settings.py`, `test_health.py`)
- All functions use `snake_case`: `extract_live_call_origin_phone()`, `normalize_phone()`, `validate_availability_payload()`
- Private/internal functions start with underscore: `_build_request()`, `_log_registered_routes()`, `_normalize_path()`
- Async functions follow same naming: `async def initialize_session()`, `async def check()`
- Local variables and parameters use `snake_case`: `arrival_date`, `caller_phone`, `owner_phone`, `twilio_client`
- Boolean variables/parameters don't require specific prefix: `enabled`, `sent`, `has_complete_twilio_config`
- Classes use `PascalCase`: `CallSession`, `Settings`, `AvailabilityChecker`, `DailyActivity`
- Custom exceptions use `PascalCase` ending in "Error": `SettingsError`, `AvailabilityValidationError`
- Constants use `SCREAMING_SNAKE_CASE`: `SUMMARY_TOPIC_KEYWORDS`, `DEFAULT_TRANSCRIPTION_PROMPT`, `TOPIC_LABELS_FI`
- Type aliases use lowercase: `ConversationLog = List[ConversationMessage]`

## Code Style

- No explicit linting/formatting tool configured (no `.eslintrc`, `.flake8`, `pyproject.toml` found)
- Import statement organization matters (see Import Organization below)
- Descriptive naming preferred over comments
- Type hints are mandatory throughout: all function parameters and return types are annotated
- Use `from __future__ import annotations` for forward references (common in this codebase: `app/services/*.py`)
- Modern type syntax preferred: `dict[str, Any]`, `list[str]` over `Dict[str, Any]`, `List[str]`
- Optional values: `Optional[str]` or `str | None` (both patterns used)
- Union types: `list[tuple[bytes, bytes]] | None` for optional lists
- Dataclass field defaults: use `field(default_factory=...)` for mutable defaults like dicts/lists

## Import Organization

- Absolute imports from `app` root: `from app.config.settings import settings` (not relative imports)

## Error Handling

- Custom exception classes extend built-in exceptions: `class SettingsError(ValueError)`, `class AvailabilityValidationError(ValueError)`
- Exception chaining with `raise ... from exc` for error context: `raise SettingsError(...) from exc`
- Try-except blocks catch specific exception types, not bare `except`:
- FastAPI uses `HTTPException` from `fastapi` with `status` codes from `fastapi.status`:
- Logging errors at appropriate levels (warn/error) with context:
- Early returns to avoid nested conditionals:

## Logging

- `logger = logging.getLogger(__name__)` in each module (`app/main.py`, `app/services/*.py`)
- Global config: `logging.basicConfig(level=logging.INFO)` in `app/config/settings.py`
- Structured log messages with named arguments: `logger.info("[startup] route_registered path=%s methods=%s name=%s", path, methods, name)`
- Log level keywords in brackets: `[startup]`, `[error]` for semantic grouping
- Use `logger.info()` for lifecycle events, `logger.warning()` for recoverable errors
- Include context variables: dates, phone numbers, status codes, configuration state

## Comments

- Code is generally self-documenting via clear names and type hints
- Comments appear mainly on custom exception classes with docstrings
- No docstrings on simple functions; code clarity preferred
- Comments explain *why*, not *what*

## Function Design

- Named parameters preferred: functions use keyword-only arguments with `*` separator where needed
- Explicit return types on all functions
- Return early for error/edge cases (guard clauses)
- Return dataclass instances for complex results (see `AvailabilityResponse`, `SendDailyDigestResult`)

## Module Design

- Use `@dataclass(frozen=True)` for immutable data structures: `CallSession` in tests uses non-frozen dataclass with methods
- Frozen dataclasses for pure data: `DailyActivity`, `DailyDigest`, `Settings` (frozen dataclass with factory method `from_env()`)
- Field defaults use `field(default_factory=...)` for mutable types:
- Dependency injection through constructor: `BookingOnlineAvailabilityChecker(fetcher)` accepts optional fetcher
- Stateless services with methods: `CallbackRequestSmsService`, `ConversationAnonymizer`
- Factory methods on configuration objects: `Settings.from_env()` as classmethod
- No barrel files (no `__init__.py` re-exports)
- Direct imports from modules: `from app.services.availability_checker import BookingOnlineAvailabilityChecker`
- `@cached_property` for computed values computed once: `twilio_client` property
- `@property` for simple computed values: `has_complete_twilio_config`, `normalized_public_base_url`
- `@classmethod` for factory methods: `Settings.from_env()`
- `@staticmethod` for utility functions not needing class state: `Settings._read_str()`, `Settings._normalize_path()`

<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

## System Overview

```text

```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| FastAPI App | Request routing, middleware, lifespan | `app/main.py` |
| Voice Router | Incoming call handling, WebSocket media stream | `app/routes/voice.py` |
| Admin Prompt Router | Prompt CRUD and system message management | `app/routes/admin_prompt.py` |
| Dashboard Router | Call analytics, session history, real-time stats | `app/routes/dashboard.py` |
| Health Router | Service health check | `app/routes/health.py` |
| Availability Router | Availability queries from web clients | `app/routes/availability.py` |
| Feedback Router | Incoming SMS feedback submissions | `app/routes/feedback.py` |
| Realtime Session | OpenAI Realtime API session initialization | `app/services/realtime_session.py` |
| Realtime Tools | Tool execution dispatch (availability, SMS tools) | `app/services/realtime_tools.py` |
| Runtime State | In-memory session storage by call_sid/stream_sid | `app/services/runtime_state.py` |
| Transcript Service | Call logging to JSON files with anonymization | `app/services/transcript_service.py` |
| Availability Checker | BookingOnline calendar availability checking | `app/services/availability_checker.py` |
| Conversation Anonymizer | LLM-powered privacy-preserving call summaries | `app/services/conversation_anonymizer.py` |
| Call Config | Configuration builder for individual calls | `app/services/call_config.py` |
| Settings | Environment-based application configuration | `app/config/settings.py` |

## Pattern Overview

- **Real-time bidirectional WebSocket:** Voice audio flows between Twilio SIP→Twilio WebSocket→OpenAI Realtime→back to Twilio
- **OpenAI Realtime tools:** Assistant can invoke availability checks, SMS tools directly during conversation
- **Privacy-first logging:** All call transcripts are anonymized via LLM before JSON file persistence
- **Stateless HTTP, stateful WebSocket:** Call state lives in in-memory session store during active streams; archived to JSON on completion
- **Multi-tenancy ready:** System message, voice, language, temperature all configurable per-call via environment defaults or payload overrides

## Layers

- Purpose: Accept incoming requests and upgrade to WebSocket connections
- Location: `app/routes/voice.py` (lines 36-86 for incoming calls, 88-170 for outbound, 171+ for media stream)
- Contains: Route handlers for call initiation, TwiML response generation, WebSocket connection management
- Depends on: Settings, session store, realtime session initialization
- Used by: Twilio service, client web applications
- Purpose: Manage WebSocket connection to OpenAI Realtime, encode/decode streaming audio and realtime events
- Location: `app/routes/voice.py` (lines 171-400+) async functions `receive_from_twilio()`, `receive_from_openai()`, `send_mark()`
- Contains: OpenAI WebSocket connection management, audio format conversion (base64 PCM), realtime event handling
- Depends on: Settings (API keys, model configuration), `websockets` library
- Used by: Media stream handler, tool execution
- Purpose: Handle domain logic—availability checking, SMS sending, anonymization, analytics
- Location: `app/services/`
- Contains: Availability checking pipeline, SMS service integrations, call transcription, conversation anonymization, daily scheduling
- Depends on: Models, HTTP clients (fetchers), external API clients (Twilio, potentially OpenAI for anonymization)
- Used by: Route handlers, realtime tools executor, scheduled tasks
- Purpose: Define call session structure, availability queries/responses, configuration objects
- Location: `app/models/call.py`, `app/models/availability.py`
- Contains: `CallSession` (with transcript entries), `CallConfig`, `AvailabilityQuery`/`AvailabilityResponse`
- Depends on: None (pure data classes)
- Used by: All service and route layers
- Purpose: Ephemeral in-memory storage of active call sessions during streaming
- Location: `app/services/runtime_state.py`
- Contains: `InMemoryCallSessionStore` with maps by call_sid and stream_sid
- Depends on: Models
- Used by: Route handlers, middleware, services that need session context
- Purpose: Environment-based app settings, defaults, validation
- Location: `app/config/settings.py`, `app/config/default_system_message.py`
- Contains: Dataclass `Settings` with all env var mappings, property methods for computed URLs, validation
- Depends on: Python standard library, `dotenv`, Twilio SDK
- Used by: Every component that needs configuration

## Data Flow

### Primary Request Path (Incoming Call → OpenAI → Response)

### Secondary Flow: Availability Check Tool

### Secondary Flow: Daily Summary Scheduler

- **During call:** `CallSession` lives in `session_store` (in-memory). Transcript entries accumulate as events arrive.
- **After call ends:** Session is finalized (timestamps, status set), passed to `save_conversation_log()` for anonymization and persistence
- **Dashboard:** Read from JSON log files on disk; aggregate analytics in `dashboard_data` service
- **Prompts:** Loaded from `prompt_store.json` at startup or on `/admin/prompt/save` POST

## Key Abstractions

- Purpose: Represents one voice call with full lifecycle (created → in_progress → completed)
- Examples: `app/models/call.py:44-99`
- Pattern: Mutable dataclass with methods to bind stream, finish, mark errors, append transcripts
- Purpose: Structured result from BookingOnline calendar check, includes status, available units with pricing, assistant message
- Examples: `app/models/availability.py`
- Pattern: Immutable dataclass with `to_dict()` method for serialization to OpenAI
- Purpose: Per-call customization of system message, voice, language, temperature, reasoning effort
- Examples: `app/models/call.py:17-24`
- Pattern: Dataclass with defaults from settings; passed through routes → realtime_session initialization
- Purpose: Map from call_sid/stream_sid to active CallSession, allowing session lookup during async operations
- Examples: `app/services/runtime_state.py:6-120`
- Pattern: Simple dict-based store; no persistence; sessions removed on disconnect or error
- Purpose: Orchestrate calendar fetch → HTML parse → calendar interpretation for availability queries
- Examples: `app/services/availability_checker.py:33-92`
- Pattern: Async class with private `_check_unit()` helper; supports concurrent unit checks with `asyncio` gathering

## Entry Points

- Location: `app/routes/voice.py:36-76`
- Triggers: Twilio webhook when new call arrives
- Responsibilities: Extract call metadata, create/update session, return TwiML with stream URL
- Location: `app/routes/voice.py:171+`
- Triggers: Client upgrades HTTP to WebSocket after `/incoming-call` TwiML redirect
- Responsibilities: Bridge Twilio media stream ↔ OpenAI Realtime API, handle tool calls, manage session lifecycle
- Location: `app/routes/voice.py:88-170`
- Triggers: External client initiates outbound call
- Responsibilities: Validate phone number, create call via Twilio API, return call_sid for tracking
- Location: `app/routes/admin_prompt.py:17-65`
- Triggers: Admin user views/edits system prompt
- Responsibilities: Load current prompt from store, display HTML form, persist changes
- Location: `app/routes/dashboard.py:722-747`
- Triggers: Web browser request
- Responsibilities: Serve HTML dashboard with analytics and call history
- Location: `app/routes/health.py:9+`
- Triggers: Container health checks
- Responsibilities: Return 200 OK or raise exception if critical dependencies missing

## Architectural Constraints

- **Threading:** Single-threaded async event loop (FastAPI/Uvicorn). CPU-bound operations like anonymization run in thread pool via `asyncio.to_thread()`.
- **Global state:** `session_store` (module-level singleton in `app/services/runtime_state.py:120`), `settings` (module-level singleton in `app/config/settings.py:568`), `DailySummaryScheduler` task (created once in lifespan).
- **Circular imports:** None detected. Layers import downward (routes → services → models → none).
- **WebSocket protocol:** Twilio sends PCM audio as base64-encoded chunks in JSON; OpenAI Realtime expects same format. Timestamps must be synchronized.
- **Real-time model compatibility:** Code checks `_supports_temperature()` and `_supports_reasoning_effort()` to conditionally include session fields; different model families have different schemas.

## Anti-Patterns

### Global Session Store Without Cleanup

### No Timeout on OpenAI WebSocket Connection

### Availability Checker Fetches HTML for Each Unit Sequentially

## Error Handling

- Web routes catch exceptions and return appropriate HTTP status + descriptive message
- WebSocket handlers log errors and close connection gracefully
- Tool handlers (availability, SMS) return structured error responses to OpenAI instead of raising
- Settings validation at startup fails fast with `SettingsError` if required env vars missing
- `try/except` with `logger.exception()` for unexpected errors
- Custom exceptions (`SettingsError`, `AvailabilityValidationError`, `BookingOnlineFetchError`) for domain-specific errors
- Structured error responses from tool handlers include `error_code` and `message_for_assistant` fields for OpenAI to relay to user
- TwiML error responses for call failures (voice message to caller, not exception traceback)

## Cross-Cutting Concerns

- Python standard `logging` module configured at startup in `settings.py:17`
- Structured log messages with context (e.g., `stream_sid`, `error_code`)
- No secrets logged (phone numbers masked, API keys not printed)
- Request payload validation in route handlers (e.g., `validate_availability_payload()` in `availability_checker.py:95-118`)
- CallConfig defaults from settings; per-call overrides validated before use
- Twilio signature verification (not implemented—assumes reverse proxy handles this)
- Admin routes use HTTP Basic Auth: username from `ADMIN_PROMPT_USERNAME`, password from `ADMIN_PROMPT_PASSWORD` (`app/routes/admin_prompt.py`)
- OpenAI/Azure auth via API key headers in realtime WebSocket
- Twilio webhook auth typically verified by reverse proxy
- Call transcripts not persisted in raw form; only anonymized LLM summaries stored
- Phone numbers masked in logs (last 4 digits only)
- Conversation anonymizer runs as opt-in service (`LOG_ANONYMIZATION_ENABLED` env var)

<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
