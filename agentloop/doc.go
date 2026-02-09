// Package agentloop implements the Coding Agent Loop specification.
//
// It provides a programmable agentic loop that pairs a large language model
// with developer tools. The loop orchestrates LLM calls, tool execution,
// context management, and provider-specific behavior into a reliable
// autonomous workflow.
//
// The agent loop uses the unifiedllm package's low-level Client.Complete()
// method directly, implementing its own turn loop to interleave tool
// execution with truncation, steering, events, and loop detection.
//
// # Architecture
//
// The package is organized around these core concepts:
//
//   - Session: The central orchestrator holding conversation state,
//     dispatching tool calls, managing events, and enforcing limits.
//   - ProviderProfile: Provider-aligned tool and prompt configuration
//     (OpenAI/codex, Anthropic/Claude Code, Gemini/gemini-cli).
//   - ExecutionEnvironment: Abstraction for where tools run (local,
//     Docker, Kubernetes, WASM, SSH).
//   - ToolRegistry: Registration and dispatch of tool definitions.
//   - EventEmitter: Typed event stream for host application integration.
//
// # Quick Start
//
//	profile := agentloop.NewAnthropicProfile("claude-opus-4-6")
//	env := agentloop.NewLocalExecutionEnvironment("/path/to/project")
//	session := agentloop.NewSession(profile, env, nil)
//	defer session.Close()
//
//	if err := session.Submit(ctx, "Create a hello.py file"); err != nil {
//	    log.Fatal(err)
//	}
//
//	for event := range session.Events() {
//	    fmt.Printf("[%s] %v\n", event.Kind, event.Data)
//	}
package agentloop
