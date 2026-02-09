package agentloop

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"

	"github.com/google/uuid"
)

// SubAgentStatus represents the lifecycle state of a subagent.
type SubAgentStatus string

const (
	SubAgentRunning   SubAgentStatus = "running"
	SubAgentCompleted SubAgentStatus = "completed"
	SubAgentFailed    SubAgentStatus = "failed"
)

// SubAgentHandle tracks a running subagent.
type SubAgentHandle struct {
	ID      string         `json:"id"`
	Session *Session       `json:"-"`
	Status  SubAgentStatus `json:"status"`
	Result  *SubAgentResult `json:"result,omitempty"`
	cancel  context.CancelFunc
	mu      sync.Mutex
}

// SubAgentResult holds the output of a completed subagent.
type SubAgentResult struct {
	Output    string `json:"output"`
	Success   bool   `json:"success"`
	TurnsUsed int    `json:"turns_used"`
}

// SubAgentManager manages child agents for a parent session.
type SubAgentManager struct {
	agents   map[string]*SubAgentHandle
	mu       sync.RWMutex
	maxDepth int
	depth    int
}

// NewSubAgentManager creates a new subagent manager.
func NewSubAgentManager(maxDepth, currentDepth int) *SubAgentManager {
	return &SubAgentManager{
		agents:   make(map[string]*SubAgentHandle),
		maxDepth: maxDepth,
		depth:    currentDepth,
	}
}

// CanSpawn returns true if nesting depth allows spawning.
func (m *SubAgentManager) CanSpawn() bool {
	return m.depth < m.maxDepth
}

// Spawn creates and starts a new subagent session.
func (m *SubAgentManager) Spawn(ctx context.Context, profile ProviderProfile, env ExecutionEnvironment, task string, config *SessionConfig) (*SubAgentHandle, error) {
	if !m.CanSpawn() {
		return nil, fmt.Errorf("maximum subagent depth (%d) reached", m.maxDepth)
	}

	id := uuid.New().String()
	subCtx, cancel := context.WithCancel(ctx)

	subConfig := DefaultSessionConfig()
	if config != nil {
		subConfig = *config
	}
	subConfig.MaxTurns = 50 // Default subagent turn limit.
	subConfig.MaxSubagentDepth = m.maxDepth
	subConfig.subagentDepth = m.depth + 1

	subSession := NewSession(profile, env, &subConfig)

	handle := &SubAgentHandle{
		ID:      id,
		Session: subSession,
		Status:  SubAgentRunning,
		cancel:  cancel,
	}

	m.mu.Lock()
	m.agents[id] = handle
	m.mu.Unlock()

	// Run subagent in background.
	go func() {
		err := subSession.Submit(subCtx, task)
		handle.mu.Lock()
		defer handle.mu.Unlock()

		turnsUsed := len(subSession.History())
		lastText := ""
		for i := len(subSession.History()) - 1; i >= 0; i-- {
			turn := subSession.History()[i]
			if turn.Kind == TurnAssistant && turn.Assistant != nil {
				lastText = turn.Assistant.Content
				break
			}
		}

		if err != nil {
			handle.Status = SubAgentFailed
			handle.Result = &SubAgentResult{
				Output:    fmt.Sprintf("Error: %v", err),
				Success:   false,
				TurnsUsed: turnsUsed,
			}
		} else {
			handle.Status = SubAgentCompleted
			handle.Result = &SubAgentResult{
				Output:    lastText,
				Success:   true,
				TurnsUsed: turnsUsed,
			}
		}
	}()

	return handle, nil
}

// Get returns a subagent handle by ID.
func (m *SubAgentManager) Get(id string) *SubAgentHandle {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.agents[id]
}

// Close terminates a subagent.
func (m *SubAgentManager) Close(id string) error {
	m.mu.Lock()
	handle, ok := m.agents[id]
	m.mu.Unlock()
	if !ok {
		return fmt.Errorf("subagent %s not found", id)
	}

	handle.cancel()
	handle.mu.Lock()
	if handle.Status == SubAgentRunning {
		handle.Status = SubAgentFailed
	}
	handle.mu.Unlock()
	return nil
}

// CloseAll terminates all active subagents.
func (m *SubAgentManager) CloseAll() {
	m.mu.RLock()
	defer m.mu.RUnlock()
	for _, handle := range m.agents {
		handle.cancel()
	}
}

// RegisterSubagentTools registers spawn_agent, send_input, wait, and
// close_agent tools on the given registry.
func RegisterSubagentTools(reg *ToolRegistry, manager *SubAgentManager, profile ProviderProfile, env ExecutionEnvironment) {
	reg.Register(RegisteredTool{
		Definition: ToolDefinition{
			Name:        "spawn_agent",
			Description: "Spawn a subagent to handle a scoped task autonomously.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"task": map[string]interface{}{
						"type":        "string",
						"description": "Natural language task description.",
					},
					"working_dir": map[string]interface{}{
						"type":        "string",
						"description": "Subdirectory to scope the agent to.",
					},
					"max_turns": map[string]interface{}{
						"type":        "integer",
						"description": "Turn limit for the subagent. Default: 50.",
					},
				},
				"required": []string{"task"},
			},
		},
		Executor: func(arguments json.RawMessage, execEnv ExecutionEnvironment) (string, error) {
			args, err := ParseToolArguments(arguments)
			if err != nil {
				return "", err
			}
			task, ok := GetStringArg(args, "task")
			if !ok || task == "" {
				return "", fmt.Errorf("task is required")
			}

			config := DefaultSessionConfig()
			if maxTurns, ok := GetIntArg(args, "max_turns"); ok && maxTurns > 0 {
				config.MaxTurns = maxTurns
			}

			handle, err := manager.Spawn(context.Background(), profile, execEnv, task, &config)
			if err != nil {
				return "", err
			}
			return fmt.Sprintf("Subagent spawned with ID: %s\nStatus: %s", handle.ID, handle.Status), nil
		},
	})

	reg.Register(RegisteredTool{
		Definition: ToolDefinition{
			Name:        "send_input",
			Description: "Send a message to a running subagent.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"agent_id": map[string]interface{}{
						"type":        "string",
						"description": "The subagent ID.",
					},
					"message": map[string]interface{}{
						"type":        "string",
						"description": "Message to send.",
					},
				},
				"required": []string{"agent_id", "message"},
			},
		},
		Executor: func(arguments json.RawMessage, execEnv ExecutionEnvironment) (string, error) {
			args, err := ParseToolArguments(arguments)
			if err != nil {
				return "", err
			}
			agentID, _ := GetStringArg(args, "agent_id")
			message, _ := GetStringArg(args, "message")

			handle := manager.Get(agentID)
			if handle == nil {
				return "", fmt.Errorf("subagent %s not found", agentID)
			}

			handle.Session.Steer(message)
			return fmt.Sprintf("Message sent to subagent %s", agentID), nil
		},
	})

	reg.Register(RegisteredTool{
		Definition: ToolDefinition{
			Name:        "wait",
			Description: "Wait for a subagent to complete and return its result.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"agent_id": map[string]interface{}{
						"type":        "string",
						"description": "The subagent ID.",
					},
				},
				"required": []string{"agent_id"},
			},
		},
		Executor: func(arguments json.RawMessage, execEnv ExecutionEnvironment) (string, error) {
			args, err := ParseToolArguments(arguments)
			if err != nil {
				return "", err
			}
			agentID, _ := GetStringArg(args, "agent_id")

			handle := manager.Get(agentID)
			if handle == nil {
				return "", fmt.Errorf("subagent %s not found", agentID)
			}

			// Poll until done.
			for {
				handle.mu.Lock()
				status := handle.Status
				result := handle.Result
				handle.mu.Unlock()

				if status != SubAgentRunning {
					if result != nil {
						return fmt.Sprintf("Status: %s\nTurns used: %d\nOutput:\n%s",
							status, result.TurnsUsed, result.Output), nil
					}
					return fmt.Sprintf("Status: %s", status), nil
				}
				// Brief sleep to avoid busy-waiting (would use proper
				// signaling in production).
			}
		},
	})

	reg.Register(RegisteredTool{
		Definition: ToolDefinition{
			Name:        "close_agent",
			Description: "Terminate a subagent.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"agent_id": map[string]interface{}{
						"type":        "string",
						"description": "The subagent ID.",
					},
				},
				"required": []string{"agent_id"},
			},
		},
		Executor: func(arguments json.RawMessage, execEnv ExecutionEnvironment) (string, error) {
			args, err := ParseToolArguments(arguments)
			if err != nil {
				return "", err
			}
			agentID, _ := GetStringArg(args, "agent_id")

			if err := manager.Close(agentID); err != nil {
				return "", err
			}
			return fmt.Sprintf("Subagent %s terminated", agentID), nil
		},
	})
}
