package agentloop

import (
	"encoding/json"
	"fmt"
	"sync"
)

// ToolExecutor is the function signature for tool execution.
// It receives parsed arguments and the execution environment.
type ToolExecutor func(arguments json.RawMessage, env ExecutionEnvironment) (string, error)

// ToolDefinition describes a tool for the LLM (serializable metadata).
type ToolDefinition struct {
	Name        string                 `json:"name"`
	Description string                 `json:"description"`
	Parameters  map[string]interface{} `json:"parameters"`
}

// RegisteredTool pairs a tool definition with its executor.
type RegisteredTool struct {
	Definition ToolDefinition
	Executor   ToolExecutor
}

// ToolRegistry manages tool registration and lookup.
type ToolRegistry struct {
	tools map[string]*RegisteredTool
	mu    sync.RWMutex
}

// NewToolRegistry creates an empty ToolRegistry.
func NewToolRegistry() *ToolRegistry {
	return &ToolRegistry{
		tools: make(map[string]*RegisteredTool),
	}
}

// Register adds or replaces a tool in the registry.
func (r *ToolRegistry) Register(tool RegisteredTool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.tools[tool.Definition.Name] = &tool
}

// Unregister removes a tool from the registry.
func (r *ToolRegistry) Unregister(name string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	delete(r.tools, name)
}

// Get returns a registered tool by name, or nil if not found.
func (r *ToolRegistry) Get(name string) *RegisteredTool {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.tools[name]
}

// Definitions returns all tool definitions (for sending to the LLM).
func (r *ToolRegistry) Definitions() []ToolDefinition {
	r.mu.RLock()
	defer r.mu.RUnlock()
	defs := make([]ToolDefinition, 0, len(r.tools))
	for _, tool := range r.tools {
		defs = append(defs, tool.Definition)
	}
	return defs
}

// Names returns the names of all registered tools.
func (r *ToolRegistry) Names() []string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	names := make([]string, 0, len(r.tools))
	for name := range r.tools {
		names = append(names, name)
	}
	return names
}

// Count returns the number of registered tools.
func (r *ToolRegistry) Count() int {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return len(r.tools)
}

// Clone returns a deep copy of the registry.
func (r *ToolRegistry) Clone() *ToolRegistry {
	r.mu.RLock()
	defer r.mu.RUnlock()
	clone := NewToolRegistry()
	for name, tool := range r.tools {
		cloned := *tool
		clone.tools[name] = &cloned
	}
	return clone
}

// MergeFrom copies all tools from other into this registry.
// Existing tools with the same name are overwritten (latest-wins).
func (r *ToolRegistry) MergeFrom(other *ToolRegistry) {
	other.mu.RLock()
	defer other.mu.RUnlock()
	r.mu.Lock()
	defer r.mu.Unlock()
	for name, tool := range other.tools {
		cloned := *tool
		r.tools[name] = &cloned
	}
}

// ToUnifiedLLMToolDefs converts registry definitions to the unifiedllm
// ToolDefinition type used by the SDK.
func (r *ToolRegistry) ToUnifiedLLMToolDefs() []struct {
	Name        string                 `json:"name"`
	Description string                 `json:"description"`
	Parameters  map[string]interface{} `json:"parameters"`
} {
	defs := r.Definitions()
	result := make([]struct {
		Name        string                 `json:"name"`
		Description string                 `json:"description"`
		Parameters  map[string]interface{} `json:"parameters"`
	}, len(defs))
	for i, d := range defs {
		result[i].Name = d.Name
		result[i].Description = d.Description
		result[i].Parameters = d.Parameters
	}
	return result
}

// ParseToolArguments is a helper that unmarshals tool call arguments into a
// map for validation and access.
func ParseToolArguments(raw json.RawMessage) (map[string]interface{}, error) {
	var args map[string]interface{}
	if err := json.Unmarshal(raw, &args); err != nil {
		return nil, fmt.Errorf("invalid tool arguments: %w", err)
	}
	return args, nil
}

// GetStringArg extracts a string argument from parsed tool arguments.
func GetStringArg(args map[string]interface{}, key string) (string, bool) {
	v, ok := args[key]
	if !ok {
		return "", false
	}
	s, ok := v.(string)
	return s, ok
}

// GetIntArg extracts an integer argument from parsed tool arguments.
func GetIntArg(args map[string]interface{}, key string) (int, bool) {
	v, ok := args[key]
	if !ok {
		return 0, false
	}
	switch n := v.(type) {
	case float64:
		return int(n), true
	case int:
		return n, true
	case json.Number:
		i, err := n.Int64()
		if err != nil {
			return 0, false
		}
		return int(i), true
	default:
		return 0, false
	}
}

// GetBoolArg extracts a boolean argument from parsed tool arguments.
func GetBoolArg(args map[string]interface{}, key string) (bool, bool) {
	v, ok := args[key]
	if !ok {
		return false, false
	}
	b, ok := v.(bool)
	return b, ok
}
