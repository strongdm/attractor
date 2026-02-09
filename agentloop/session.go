package agentloop

import (
	"context"
	"fmt"
	"sync"

	"github.com/google/uuid"
	"github.com/martinemde/attractor/unifiedllm"
)

// SessionState represents the current lifecycle state of a session.
type SessionState string

const (
	StateIdle          SessionState = "idle"
	StateProcessing    SessionState = "processing"
	StateAwaitingInput SessionState = "awaiting_input"
	StateClosed        SessionState = "closed"
)

// SessionConfig holds configuration for a session.
type SessionConfig struct {
	MaxTurns                int            `json:"max_turns"`                   // 0 = unlimited
	MaxToolRoundsPerInput   int            `json:"max_tool_rounds_per_input"`   // per user input
	DefaultCommandTimeoutMs int            `json:"default_command_timeout_ms"`
	MaxCommandTimeoutMs     int            `json:"max_command_timeout_ms"`
	ReasoningEffort         string         `json:"reasoning_effort,omitempty"`  // "low", "medium", "high", or ""
	ToolOutputLimits        map[string]int `json:"tool_output_limits,omitempty"`
	ToolLineLimits          map[string]int `json:"tool_line_limits,omitempty"`
	EnableLoopDetection     bool           `json:"enable_loop_detection"`
	LoopDetectionWindow     int            `json:"loop_detection_window"`
	MaxSubagentDepth        int            `json:"max_subagent_depth"`
	UserInstructions        string         `json:"user_instructions,omitempty"` // appended last to system prompt
	subagentDepth           int            // internal: current nesting depth
}

// DefaultSessionConfig returns the spec-default configuration.
func DefaultSessionConfig() SessionConfig {
	return SessionConfig{
		MaxTurns:                0,   // unlimited
		MaxToolRoundsPerInput:   200,
		DefaultCommandTimeoutMs: 10000,  // 10 seconds
		MaxCommandTimeoutMs:     600000, // 10 minutes
		EnableLoopDetection:     true,
		LoopDetectionWindow:     10,
		MaxSubagentDepth:        1,
	}
}

// Session is the central orchestrator for the agentic loop.
type Session struct {
	id             string
	profile        ProviderProfile
	env            ExecutionEnvironment
	history        []Turn
	emitter        *EventEmitter
	config         SessionConfig
	state          SessionState
	llmClient      *unifiedllm.Client
	steeringQueue  []string
	followupQueue  []string
	subagents      *SubAgentManager
	abortSignaled  bool
	mu             sync.Mutex
}

// NewSession creates a new session with the given profile, execution
// environment, and optional configuration.
func NewSession(profile ProviderProfile, env ExecutionEnvironment, config *SessionConfig) *Session {
	sessionID := uuid.New().String()

	cfg := DefaultSessionConfig()
	if config != nil {
		cfg = *config
	}

	s := &Session{
		id:        sessionID,
		profile:   profile,
		env:       env,
		history:   make([]Turn, 0),
		emitter:   NewEventEmitter(sessionID, 256),
		config:    cfg,
		state:     StateIdle,
		llmClient: unifiedllm.GetDefaultClient(),
		subagents: NewSubAgentManager(cfg.MaxSubagentDepth, cfg.subagentDepth),
	}

	// Register subagent tools if depth allows.
	if s.subagents.CanSpawn() {
		RegisterSubagentTools(profile.ToolRegistry(), s.subagents, profile, env)
	}

	return s
}

// SetClient sets a custom LLM client (overriding the default).
func (s *Session) SetClient(client *unifiedllm.Client) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.llmClient = client
}

// ID returns the session identifier.
func (s *Session) ID() string { return s.id }

// State returns the current session state.
func (s *Session) State() SessionState {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.state
}

// History returns a copy of the conversation history.
func (s *Session) History() []Turn {
	s.mu.Lock()
	defer s.mu.Unlock()
	h := make([]Turn, len(s.history))
	copy(h, s.history)
	return h
}

// Events returns the event channel for the host application.
func (s *Session) Events() <-chan SessionEvent {
	return s.emitter.Events()
}

// Steer queues a message to be injected after the current tool round.
func (s *Session) Steer(message string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.steeringQueue = append(s.steeringQueue, message)
}

// FollowUp queues a message to be processed after the current input completes.
func (s *Session) FollowUp(message string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.followupQueue = append(s.followupQueue, message)
}

// Abort signals the session to stop processing.
func (s *Session) Abort() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.abortSignaled = true
}

// Close terminates the session and cleans up resources.
func (s *Session) Close() {
	s.mu.Lock()
	s.state = StateClosed
	s.mu.Unlock()

	s.subagents.CloseAll()
	s.emitter.Emit(EventSessionEnd, map[string]interface{}{
		"state": string(StateClosed),
	})
	s.emitter.Close()
}

// SetReasoningEffort changes the reasoning effort for subsequent LLM calls.
func (s *Session) SetReasoningEffort(effort string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.config.ReasoningEffort = effort
}

// Submit processes a user input through the agentic loop.
func (s *Session) Submit(ctx context.Context, userInput string) error {
	s.mu.Lock()
	if s.state == StateClosed {
		s.mu.Unlock()
		return fmt.Errorf("session is closed")
	}
	s.state = StateProcessing
	s.abortSignaled = false
	s.mu.Unlock()

	return s.processInput(ctx, userInput)
}

// processInput is the core agentic loop (Section 2.5 of the spec).
func (s *Session) processInput(ctx context.Context, userInput string) error {
	// Append user turn.
	s.mu.Lock()
	s.history = append(s.history, NewUserTurn(userInput))
	s.mu.Unlock()
	s.emitter.Emit(EventUserInput, map[string]interface{}{
		"content": userInput,
	})

	// Drain any pending steering messages before the first LLM call.
	s.drainSteering()

	roundCount := 0

	for {
		// 1. Check limits.
		s.mu.Lock()
		maxRounds := s.config.MaxToolRoundsPerInput
		maxTurns := s.config.MaxTurns
		aborted := s.abortSignaled
		s.mu.Unlock()

		if roundCount >= maxRounds {
			s.emitter.Emit(EventTurnLimit, map[string]interface{}{
				"round": roundCount,
			})
			break
		}

		if maxTurns > 0 && s.countTurns() >= maxTurns {
			s.emitter.Emit(EventTurnLimit, map[string]interface{}{
				"total_turns": s.countTurns(),
			})
			break
		}

		if aborted {
			break
		}

		// Check context cancellation.
		select {
		case <-ctx.Done():
			s.mu.Lock()
			s.state = StateClosed
			s.mu.Unlock()
			s.emitter.Emit(EventError, map[string]interface{}{
				"error": "context cancelled",
			})
			return ctx.Err()
		default:
		}

		// 2. Build LLM request using provider profile.
		projectDocs := DiscoverProjectDocs(s.env.WorkingDirectory(), s.profile.ID())
		systemPrompt := s.profile.BuildSystemPrompt(s.env, projectDocs)

		// Append user instructions if configured.
		s.mu.Lock()
		if s.config.UserInstructions != "" {
			systemPrompt += "\n\n# User Instructions\n\n" + s.config.UserInstructions
		}
		s.mu.Unlock()

		messages := ConvertHistoryToMessages(s.History())

		// Build tool definitions for the request.
		toolDefs := s.profile.Tools()
		sdkToolDefs := make([]unifiedllm.ToolDefinition, len(toolDefs))
		for i, td := range toolDefs {
			sdkToolDefs[i] = unifiedllm.ToolDefinition{
				Name:        td.Name,
				Description: td.Description,
				Parameters:  td.Parameters,
			}
		}

		s.mu.Lock()
		reasoningEffort := s.config.ReasoningEffort
		s.mu.Unlock()

		request := unifiedllm.Request{
			Model:           s.profile.ModelID(),
			Messages:        append([]unifiedllm.Message{unifiedllm.SystemMessage(systemPrompt)}, messages...),
			ToolDefs:        sdkToolDefs,
			ToolChoice:      &unifiedllm.ToolChoice{Mode: "auto"},
			ReasoningEffort: reasoningEffort,
			Provider:        s.profile.ID(),
			ProviderOptions: s.profile.ProviderOptions(),
		}

		// 3. Call LLM via Unified LLM SDK.
		s.emitter.Emit(EventAssistantTextStart, nil)
		response, err := s.llmClient.Complete(ctx, request)
		if err != nil {
			// Check if it's a non-retryable error.
			if !unifiedllm.IsRetryable(err) {
				s.mu.Lock()
				s.state = StateClosed
				s.mu.Unlock()
				s.emitter.Emit(EventError, map[string]interface{}{
					"error": err.Error(),
				})
				return fmt.Errorf("unrecoverable LLM error: %w", err)
			}
			// For retryable errors, the SDK should handle retry.
			// If we still get an error, surface it.
			s.emitter.Emit(EventError, map[string]interface{}{
				"error": err.Error(),
			})
			return fmt.Errorf("LLM error after retries: %w", err)
		}

		// 4. Record assistant turn.
		toolCalls := response.ToolCallsFromResponse()
		assistantTurn := NewAssistantTurn(
			response.Text(),
			toolCalls,
			response.Reasoning(),
			response.Usage,
			response.ID,
		)
		s.mu.Lock()
		s.history = append(s.history, assistantTurn)
		s.mu.Unlock()

		s.emitter.Emit(EventAssistantTextEnd, map[string]interface{}{
			"text":      response.Text(),
			"reasoning": response.Reasoning(),
		})

		// 5. Context window awareness check.
		s.checkContextUsage()

		// 6. If no tool calls, natural completion.
		if len(toolCalls) == 0 {
			break
		}

		// 7. Execute tool calls through the execution environment.
		roundCount++
		results := s.executeToolCalls(ctx, toolCalls)
		s.mu.Lock()
		s.history = append(s.history, NewToolResultsTurn(results))
		s.mu.Unlock()

		// 8. Drain steering messages injected during tool execution.
		s.drainSteering()

		// 9. Loop detection.
		s.mu.Lock()
		enableLoop := s.config.EnableLoopDetection
		loopWindow := s.config.LoopDetectionWindow
		historyCopy := make([]Turn, len(s.history))
		copy(historyCopy, s.history)
		s.mu.Unlock()

		if enableLoop {
			if DetectLoop(historyCopy, loopWindow) {
				warning := fmt.Sprintf("Loop detected: the last %d tool calls follow a repeating pattern. Try a different approach.", loopWindow)
				s.mu.Lock()
				s.history = append(s.history, NewSteeringTurn(warning))
				s.mu.Unlock()
				s.emitter.Emit(EventLoopDetection, map[string]interface{}{
					"message": warning,
				})
			}
		}
	}

	// Process follow-up messages if any are queued.
	s.mu.Lock()
	if len(s.followupQueue) > 0 {
		nextInput := s.followupQueue[0]
		s.followupQueue = s.followupQueue[1:]
		s.mu.Unlock()
		return s.processInput(ctx, nextInput)
	}
	s.state = StateIdle
	s.mu.Unlock()
	s.emitter.Emit(EventSessionEnd, nil)

	return nil
}

// drainSteering injects all queued steering messages into the history.
func (s *Session) drainSteering() {
	s.mu.Lock()
	messages := make([]string, len(s.steeringQueue))
	copy(messages, s.steeringQueue)
	s.steeringQueue = s.steeringQueue[:0]
	s.mu.Unlock()

	for _, msg := range messages {
		s.mu.Lock()
		s.history = append(s.history, NewSteeringTurn(msg))
		s.mu.Unlock()
		s.emitter.Emit(EventSteeringInjected, map[string]interface{}{
			"content": msg,
		})
	}
}

// executeToolCalls dispatches tool calls through the registry and execution
// environment, handling parallel execution when supported.
func (s *Session) executeToolCalls(ctx context.Context, toolCalls []unifiedllm.ToolCall) []unifiedllm.ToolResult {
	if s.profile.SupportsParallelToolCalls() && len(toolCalls) > 1 {
		return s.executeToolCallsParallel(ctx, toolCalls)
	}
	return s.executeToolCallsSequential(ctx, toolCalls)
}

func (s *Session) executeToolCallsSequential(ctx context.Context, toolCalls []unifiedllm.ToolCall) []unifiedllm.ToolResult {
	results := make([]unifiedllm.ToolResult, len(toolCalls))
	for i, tc := range toolCalls {
		results[i] = s.executeSingleTool(ctx, tc)
	}
	return results
}

func (s *Session) executeToolCallsParallel(ctx context.Context, toolCalls []unifiedllm.ToolCall) []unifiedllm.ToolResult {
	results := make([]unifiedllm.ToolResult, len(toolCalls))
	var wg sync.WaitGroup
	for i, tc := range toolCalls {
		wg.Add(1)
		go func(idx int, call unifiedllm.ToolCall) {
			defer wg.Done()
			results[idx] = s.executeSingleTool(ctx, call)
		}(i, tc)
	}
	wg.Wait()
	return results
}

// executeSingleTool handles the full tool execution pipeline:
// lookup -> execute -> truncate -> emit -> return
func (s *Session) executeSingleTool(_ context.Context, toolCall unifiedllm.ToolCall) unifiedllm.ToolResult {
	s.emitter.Emit(EventToolCallStart, map[string]interface{}{
		"tool_name": toolCall.Name,
		"call_id":   toolCall.ID,
	})

	// 1. Lookup tool in registry.
	registered := s.profile.ToolRegistry().Get(toolCall.Name)
	if registered == nil {
		errorMsg := fmt.Sprintf("Unknown tool: %s", toolCall.Name)
		s.emitter.Emit(EventToolCallEnd, map[string]interface{}{
			"call_id": toolCall.ID,
			"error":   errorMsg,
		})
		return unifiedllm.ToolResult{
			ToolCallID: toolCall.ID,
			Content:    errorMsg,
			IsError:    true,
		}
	}

	// 2. Execute via execution environment.
	rawOutput, err := registered.Executor(toolCall.Arguments, s.env)
	if err != nil {
		errorMsg := fmt.Sprintf("Tool error (%s): %v", toolCall.Name, err)
		s.emitter.Emit(EventToolCallEnd, map[string]interface{}{
			"call_id": toolCall.ID,
			"error":   errorMsg,
		})
		return unifiedllm.ToolResult{
			ToolCallID: toolCall.ID,
			Content:    errorMsg,
			IsError:    true,
		}
	}

	// 3. Truncate output before sending to LLM.
	s.mu.Lock()
	charLimits := s.config.ToolOutputLimits
	lineLimits := s.config.ToolLineLimits
	s.mu.Unlock()
	truncatedOutput := TruncateToolOutput(rawOutput, toolCall.Name, charLimits, lineLimits)

	// 4. Emit full output via event stream (not truncated).
	s.emitter.Emit(EventToolCallEnd, map[string]interface{}{
		"call_id": toolCall.ID,
		"output":  rawOutput, // Full untruncated output.
	})

	// 5. Return truncated output as ToolResult.
	return unifiedllm.ToolResult{
		ToolCallID: toolCall.ID,
		Content:    truncatedOutput,
		IsError:    false,
	}
}

// countTurns returns the number of user and assistant turns in the history.
func (s *Session) countTurns() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	count := 0
	for _, turn := range s.history {
		if turn.Kind == TurnUser || turn.Kind == TurnAssistant {
			count++
		}
	}
	return count
}

// checkContextUsage emits a warning if context usage exceeds 80%.
func (s *Session) checkContextUsage() {
	s.mu.Lock()
	history := make([]Turn, len(s.history))
	copy(history, s.history)
	contextWindow := s.profile.ContextWindowSize()
	s.mu.Unlock()

	totalChars := 0
	for _, turn := range history {
		totalChars += len(turn.TextContent())
		if turn.Kind == TurnToolResults && turn.ToolResults != nil {
			for _, r := range turn.ToolResults.Results {
				if s, ok := r.Content.(string); ok {
					totalChars += len(s)
				}
			}
		}
	}

	approxTokens := totalChars / 4
	threshold := int(float64(contextWindow) * 0.8)
	if approxTokens > threshold {
		pct := int(float64(approxTokens) / float64(contextWindow) * 100)
		s.emitter.Emit(EventWarning, map[string]interface{}{
			"message": fmt.Sprintf("Context usage at ~%d%% of context window", pct),
		})
	}
}
