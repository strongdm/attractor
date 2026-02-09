package agentloop

import (
	"time"

	"github.com/martinemde/attractor/unifiedllm"
)

// TurnKind discriminates between turn types.
type TurnKind string

const (
	TurnUser        TurnKind = "user"
	TurnAssistant   TurnKind = "assistant"
	TurnToolResults TurnKind = "tool_results"
	TurnSystem      TurnKind = "system"
	TurnSteering    TurnKind = "steering"
)

// Turn is a single entry in the conversation history.
type Turn struct {
	Kind      TurnKind    `json:"kind"`
	Timestamp time.Time   `json:"timestamp"`
	User      *UserTurn   `json:"user,omitempty"`
	Assistant *AssistantTurn `json:"assistant,omitempty"`
	ToolResults *ToolResultsTurn `json:"tool_results,omitempty"`
	System    *SystemTurn `json:"system,omitempty"`
	Steering  *SteeringTurn `json:"steering,omitempty"`
}

// UserTurn holds user input.
type UserTurn struct {
	Content string `json:"content"`
}

// AssistantTurn holds the model's response.
type AssistantTurn struct {
	Content    string               `json:"content"`
	ToolCalls  []unifiedllm.ToolCall `json:"tool_calls,omitempty"`
	Reasoning  string               `json:"reasoning,omitempty"`
	Usage      unifiedllm.Usage     `json:"usage"`
	ResponseID string               `json:"response_id,omitempty"`
}

// ToolResultsTurn holds tool execution results.
type ToolResultsTurn struct {
	Results []unifiedllm.ToolResult `json:"results"`
}

// SystemTurn holds a system message.
type SystemTurn struct {
	Content string `json:"content"`
}

// SteeringTurn holds an injected steering message.
type SteeringTurn struct {
	Content string `json:"content"`
}

// NewUserTurn creates a Turn wrapping user input.
func NewUserTurn(content string) Turn {
	return Turn{
		Kind:      TurnUser,
		Timestamp: time.Now(),
		User:      &UserTurn{Content: content},
	}
}

// NewAssistantTurn creates a Turn wrapping an assistant response.
func NewAssistantTurn(content string, toolCalls []unifiedllm.ToolCall, reasoning string, usage unifiedllm.Usage, responseID string) Turn {
	return Turn{
		Kind:      TurnAssistant,
		Timestamp: time.Now(),
		Assistant: &AssistantTurn{
			Content:    content,
			ToolCalls:  toolCalls,
			Reasoning:  reasoning,
			Usage:      usage,
			ResponseID: responseID,
		},
	}
}

// NewToolResultsTurn creates a Turn wrapping tool results.
func NewToolResultsTurn(results []unifiedllm.ToolResult) Turn {
	return Turn{
		Kind:        TurnToolResults,
		Timestamp:   time.Now(),
		ToolResults: &ToolResultsTurn{Results: results},
	}
}

// NewSystemTurn creates a Turn wrapping a system message.
func NewSystemTurn(content string) Turn {
	return Turn{
		Kind:      TurnSystem,
		Timestamp: time.Now(),
		System:    &SystemTurn{Content: content},
	}
}

// NewSteeringTurn creates a Turn wrapping a steering message.
func NewSteeringTurn(content string) Turn {
	return Turn{
		Kind:      TurnSteering,
		Timestamp: time.Now(),
		Steering:  &SteeringTurn{Content: content},
	}
}

// TextContent returns the text content of a turn regardless of its kind.
func (t Turn) TextContent() string {
	switch t.Kind {
	case TurnUser:
		if t.User != nil {
			return t.User.Content
		}
	case TurnAssistant:
		if t.Assistant != nil {
			return t.Assistant.Content
		}
	case TurnSystem:
		if t.System != nil {
			return t.System.Content
		}
	case TurnSteering:
		if t.Steering != nil {
			return t.Steering.Content
		}
	}
	return ""
}

// ConvertHistoryToMessages converts the turn-based history into LLM messages.
func ConvertHistoryToMessages(history []Turn) []unifiedllm.Message {
	var messages []unifiedllm.Message
	for _, turn := range history {
		switch turn.Kind {
		case TurnUser:
			if turn.User != nil {
				messages = append(messages, unifiedllm.UserMessage(turn.User.Content))
			}
		case TurnAssistant:
			if turn.Assistant != nil {
				msg := unifiedllm.AssistantMessage(turn.Assistant.Content)
				// Add tool call content parts if present.
				for _, tc := range turn.Assistant.ToolCalls {
					msg.Content = append(msg.Content,
						unifiedllm.ToolCallPart(tc.ID, tc.Name, tc.Arguments))
				}
				messages = append(messages, msg)
			}
		case TurnToolResults:
			if turn.ToolResults != nil {
				for _, result := range turn.ToolResults.Results {
					contentStr := ""
					if s, ok := result.Content.(string); ok {
						contentStr = s
					}
					messages = append(messages,
						unifiedllm.ToolResultMessage(result.ToolCallID, contentStr, result.IsError))
				}
			}
		case TurnSystem:
			if turn.System != nil {
				messages = append(messages, unifiedllm.SystemMessage(turn.System.Content))
			}
		case TurnSteering:
			// Steering turns are sent as user messages so the model treats
			// them as additional instructions.
			if turn.Steering != nil {
				messages = append(messages, unifiedllm.UserMessage(turn.Steering.Content))
			}
		}
	}
	return messages
}
