package agentloop

import (
	"sync"
	"time"
)

// EventKind identifies the type of session event.
type EventKind string

const (
	EventSessionStart        EventKind = "session_start"
	EventSessionEnd          EventKind = "session_end"
	EventUserInput           EventKind = "user_input"
	EventAssistantTextStart  EventKind = "assistant_text_start"
	EventAssistantTextDelta  EventKind = "assistant_text_delta"
	EventAssistantTextEnd    EventKind = "assistant_text_end"
	EventToolCallStart       EventKind = "tool_call_start"
	EventToolCallOutputDelta EventKind = "tool_call_output_delta"
	EventToolCallEnd         EventKind = "tool_call_end"
	EventSteeringInjected    EventKind = "steering_injected"
	EventTurnLimit           EventKind = "turn_limit"
	EventLoopDetection       EventKind = "loop_detection"
	EventWarning             EventKind = "warning"
	EventError               EventKind = "error"
)

// SessionEvent is a typed event emitted by the agent loop.
type SessionEvent struct {
	Kind      EventKind              `json:"kind"`
	Timestamp time.Time              `json:"timestamp"`
	SessionID string                 `json:"session_id"`
	Data      map[string]interface{} `json:"data,omitempty"`
}

// EventEmitter delivers typed events to the host application via a channel.
type EventEmitter struct {
	sessionID string
	ch        chan SessionEvent
	closed    bool
	mu        sync.Mutex
}

// NewEventEmitter creates a new EventEmitter with a buffered channel.
func NewEventEmitter(sessionID string, bufferSize int) *EventEmitter {
	if bufferSize <= 0 {
		bufferSize = 256
	}
	return &EventEmitter{
		sessionID: sessionID,
		ch:        make(chan SessionEvent, bufferSize),
	}
}

// Emit sends an event to the channel. If the emitter is closed, the event
// is silently dropped.
func (e *EventEmitter) Emit(kind EventKind, data map[string]interface{}) {
	e.mu.Lock()
	defer e.mu.Unlock()
	if e.closed {
		return
	}
	event := SessionEvent{
		Kind:      kind,
		Timestamp: time.Now(),
		SessionID: e.sessionID,
		Data:      data,
	}
	select {
	case e.ch <- event:
	default:
		// Channel full; drop event to avoid blocking the agent loop.
	}
}

// Events returns the read-only event channel.
func (e *EventEmitter) Events() <-chan SessionEvent {
	return e.ch
}

// Close closes the event channel. Safe to call multiple times.
func (e *EventEmitter) Close() {
	e.mu.Lock()
	defer e.mu.Unlock()
	if !e.closed {
		e.closed = true
		close(e.ch)
	}
}
