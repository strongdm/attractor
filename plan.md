# Attractor Implementation Plan

## Context

The `attractor` repo contains three NLSpecs (~5,700 lines total) and zero implementation code. The goal is to implement the complete Attractor system in Python, following TDD, DRY, and YAGNI principles. The three specs form a dependency chain:

1. **Unified LLM Client** - Multi-provider LLM client (foundation)
2. **Coding Agent Loop** - Programmable agentic coding loop (depends on #1)
3. **Attractor Pipeline Runner** - DOT-based pipeline orchestrator (depends on #1 and #2)

## Architecture

### Monorepo with Three Packages

```
attractor/
  pyproject.toml                    # workspace root (dev deps, ruff/pytest config)
  packages/
    attractor-llm/                  # Unified LLM Client
      pyproject.toml
      src/attractor_llm/
        __init__.py
        types.py                    # Message, ContentPart, Role, etc.
        request.py                  # Request, ToolDefinition, ToolChoice
        response.py                 # Response, FinishReason, Usage, StreamEvent
        errors.py                   # SDKError hierarchy
        client.py                   # Client, middleware, provider routing
        catalog.py                  # ModelInfo, model catalog
        sse.py                      # SSE parser utility
        retry.py                    # RetryPolicy, exponential backoff
        highlevel.py                # generate(), stream(), generate_object()
        adapters/
          base.py                   # ProviderAdapter ABC
          openai.py                 # Responses API adapter
          anthropic.py              # Messages API adapter
          gemini.py                 # Gemini API adapter
          openai_compat.py          # Chat Completions compat adapter
      tests/

    attractor-agent/                # Coding Agent Loop
      pyproject.toml
      src/attractor_agent/
        __init__.py
        session.py                  # Session, SessionConfig, SessionState
        turns.py                    # UserTurn, AssistantTurn, etc.
        events.py                   # EventKind, SessionEvent, EventEmitter
        loop.py                     # process_input(), loop detection
        execution.py                # ExecutionEnvironment, LocalExecutionEnvironment
        truncation.py               # Output truncation (char + line)
        subagent.py                 # Subagent spawning/management
        tools/
          registry.py               # ToolRegistry, RegisteredTool
          read_file.py, write_file.py, edit_file.py
          shell.py, grep.py, glob.py, apply_patch.py
        profiles/
          base.py                   # ProviderProfile ABC
          openai.py, anthropic.py, gemini.py
      tests/

    attractor/                      # Pipeline Runner
      pyproject.toml
      src/attractor/
        __init__.py
        parser/
          ast.py                    # Graph, Node, Edge
          lexer.py                  # DOT tokenizer
          parser.py                 # DOT parser
        validation.py               # Lint rules
        condition.py                # Condition expression evaluator
        stylesheet.py               # Model stylesheet parser
        context.py                  # Context key-value store
        checkpoint.py               # Save/load/resume
        outcome.py                  # Outcome, StageStatus
        engine.py                   # Execution loop, edge selection
        handlers/                   # All node handlers
        interviewer/                # Human-in-the-loop
        transforms.py, artifacts.py, events.py, runner.py
      tests/
```

### Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Data models | `dataclasses` | YAGNI - no pydantic overhead |
| HTTP client | `httpx` | Async support, modern, good test story |
| Async | `asyncio` native | Streaming requires it |
| Test HTTP mocking | `respx` | Pairs with httpx |
| Python version | 3.12+ | Modern features |
| Package manager | `uv` | Fast, workspace support |

### YAGNI Exclusions (defer until needed)

- HTTP server mode for pipeline runner
- Context fidelity modes beyond `compact`/`truncate` (summary modes need LLM summarization)
- `stream_object()` high-level API
- Docker/K8s/WASM/SSH execution environments
- MCP integration, sandbox/security policies

## Implementation Phases

Each phase: write failing tests -> implement -> refactor -> commit.

### Component 1: Unified LLM Client (`attractor-llm`)

**Phase 1: Project scaffolding + core types**
- Root pyproject.toml, attractor-llm package setup
- `Role`, `ContentKind` enums; `ImageData`, `AudioData`, `DocumentData`, `ToolCallData`, `ToolResultData`, `ThinkingData`
- `ContentPart` tagged union, `Message` with convenience constructors + `.text` property

**Phase 2: Request and response types**
- `ToolDefinition`, `ToolChoice`, `ResponseFormat`, `Request`
- `FinishReason`, `Usage` (with `__add__`), `Warning`, `RateLimitInfo`, `Response` (with `.text`, `.tool_calls`, `.reasoning`)
- `ToolCall`, `ToolResult`, `StreamEvent`, `StreamEventType`

**Phase 3: Error hierarchy**
- Full `SDKError` -> `ProviderError` -> specific errors (Auth, RateLimit, Server, etc.)
- `error_from_status_code()` factory, message-based classification heuristics

**Phase 4: Retry policy**
- `RetryPolicy` dataclass, `delay_for_attempt()` with exponential backoff + jitter
- `retry()` async helper, Retry-After header handling

**Phase 5: SSE parser**
- Async SSE parser for httpx response streams
- Handles event/data/retry/comments/multi-line data

**Phase 6: Provider adapter interface + Client core**
- `ProviderAdapter` ABC (complete, stream, close, initialize)
- `Client` with provider routing, middleware chain (onion pattern)

**Phase 7: Model catalog**
- `ModelInfo` dataclass, current model data
- `get_model_info()`, `list_models()`, `get_latest_model()`

**Phase 8: Anthropic adapter - request translation**
- System extraction, strict alternation (merge consecutive same-role), content part translation
- cache_control injection, beta headers, thinking block round-tripping

**Phase 9: Anthropic adapter - HTTP + response + streaming**
- `complete()` via `/v1/messages`, response translation
- `stream()` with Anthropic SSE events -> unified StreamEvent
- Error translation (using respx mocks for tests)

**Phase 10: OpenAI adapter - request translation (Responses API)**
- System -> `instructions`, messages -> `input` array (message, function_call, function_call_output items)
- reasoning.effort mapping, tool definitions

**Phase 11: OpenAI adapter - HTTP + response + streaming**
- `complete()` via `/v1/responses`, reasoning_tokens extraction
- `stream()` with Responses API events -> unified StreamEvent

**Phase 12: Gemini adapter**
- Full adapter: systemInstruction, user/model roles, functionCall/functionResponse
- Synthetic tool call ID generation, `?alt=sse` streaming
- `key` query param auth, thoughtsTokenCount -> reasoning_tokens

**Phase 13: OpenAI-compatible adapter**
- Chat Completions format for third-party endpoints

**Phase 14: Client.from_env() + generate()**
- Wire env var detection -> adapter instantiation
- `generate()`: prompt standardization, tool execution loop, StepResult/GenerateResult, Usage aggregation

**Phase 15: stream(), generate_object(), StreamAccumulator**
- `stream()` with tool execution between steps
- `StreamResult`, `StreamAccumulator`
- `generate_object()` with schema injection per provider

**Phase 16: Prompt caching verification**
- Refine Anthropic cache_control injection
- Verify cache token mapping across all providers

### Component 2: Coding Agent Loop (`attractor-agent`)

**Phase 17: Package scaffolding + turn types + events**
- Turn types (UserTurn, AssistantTurn, ToolResultsTurn, SystemTurn, SteeringTurn)
- EventKind enum, SessionEvent, EventEmitter

**Phase 18: Tool output truncation**
- `truncate_output()` (head_tail, tail modes), `truncate_lines()`
- `truncate_tool_output()` pipeline (chars first, then lines)
- Default limits table

**Phase 19: Tool registry + execution environment interface**
- `RegisteredTool`, `ToolRegistry`
- `ExecutionEnvironment` ABC, `ExecResult`, `DirEntry`

**Phase 20: LocalExecutionEnvironment + shell tool**
- File ops, `exec_command()` with process group + timeout (SIGTERM -> SIGKILL)
- Env var filtering, shell tool wrapper

**Phase 21: File tools (read_file, write_file, edit_file)**
- Line-numbered output, offset/limit, parent dir creation, exact-match editing

**Phase 22: Search tools (grep, glob) + apply_patch**
- Regex search, glob with mtime sort
- v4a patch format parser for OpenAI profile

**Phase 23: Provider profiles**
- `ProviderProfile` ABC
- Anthropic (Claude Code-aligned), OpenAI (codex-rs-aligned), Gemini profiles
- System prompt generation, tool registration

**Phase 24: Session + core agentic loop**
- `SessionConfig`, `SessionState`, `Session`
- `process_input()`: LLM call -> tool execution -> loop
- `convert_history_to_messages()`

**Phase 25: Steering, follow-up, loop detection**
- `steer()`, `follow_up()` queues
- `detect_loop()` pattern matching (lengths 1, 2, 3)

**Phase 26: Subagent support**
- spawn_agent, send_input, wait, close_agent tools
- Depth limiting, shared ExecutionEnvironment

### Component 3: Pipeline Runner (`attractor`)

**Phase 27: DOT parser**
- AST types (Graph, Node, Edge)
- Lexer (tokens, comments, all value types)
- Parser (digraph, nodes, edges, chained edges, defaults, subgraphs)

**Phase 28: Validation + condition language + stylesheet**
- All lint rules (start_node, reachability, etc.), validate(), validate_or_raise()
- Condition parser/evaluator (=, !=, &&, context.* resolution)
- Stylesheet parser (*, .class, #id selectors, specificity)

**Phase 29: Context, checkpoint, outcome, handlers, interviewer**
- Thread-safe Context, Checkpoint save/load, Outcome + StageStatus
- All handlers: start, exit, codergen, wait.human, conditional, parallel, fan_in, tool, manager_loop
- Interviewer interface + implementations (AutoApprove, Console, Callback, Queue, Recording)

**Phase 30: Execution engine + transforms + runner**
- Core loop: find_start -> execute -> select_edge -> advance
- Edge selection (5-step priority), execute_with_retry(), goal gate enforcement
- Variable expansion + stylesheet transforms
- ArtifactStore, pipeline events, top-level `run()`

## Verification

After each component is complete, run integration tests:

- **After Phase 16**: Test all three LLM adapters against real APIs (text gen, streaming, tools, structured output, error handling)
- **After Phase 26**: Test a real coding agent session (file creation, editing, shell execution)
- **After Phase 30**: Test a full DOT pipeline run end-to-end

Unit tests at every phase use mocked HTTP (respx) and in-memory fixtures.

## Critical Spec References

- `unified-llm-spec.md` Section 3 (Provider Adapters) - drives adapter implementation
- `unified-llm-spec.md` Section 6 (Error Handling) - drives error hierarchy
- `coding-agent-loop-spec.md` Section 2.5-2.7 (Provider Profiles) - drives tool selection per provider
- `coding-agent-loop-spec.md` Section 2.8 (Truncation) - drives output handling
- `attractor-spec.md` Section 2 (DOT DSL) - drives parser grammar
- `attractor-spec.md` Section 3 (Execution Engine) - drives core loop + edge selection
