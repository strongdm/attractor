package agentloop

import (
	"fmt"
	"strings"
)

// AnthropicProfile provides Claude Code-aligned tools and system prompts
// for Anthropic models (Claude Opus, Sonnet, Haiku).
type AnthropicProfile struct {
	BaseProfile
}

// NewAnthropicProfile creates a profile for Anthropic models.
func NewAnthropicProfile(model string) *AnthropicProfile {
	p := &AnthropicProfile{
		BaseProfile: BaseProfile{
			providerID:                "anthropic",
			model:                     model,
			registry:                  NewToolRegistry(),
			supportsReasoning:         true,
			supportsStreaming:          true,
			supportsParallelToolCalls: true,
			contextWindowSize:         200000,
		},
	}

	// Register Claude Code-aligned core tools.
	// Anthropic uses edit_file with old_string/new_string as the native format.
	RegisterCoreTools(p.registry, 120000, 600000) // 120s default timeout per Claude Code convention.

	return p
}

// BuildSystemPrompt constructs the Anthropic/Claude Code-aligned system prompt.
func (p *AnthropicProfile) BuildSystemPrompt(env ExecutionEnvironment, projectDocs string) string {
	var sb strings.Builder

	// 1. Provider-specific base instructions (Claude Code-aligned).
	sb.WriteString(anthropicBasePrompt)
	sb.WriteString("\n\n")

	// 2. Environment context.
	sb.WriteString(BuildEnvironmentContext(env, p.model))
	sb.WriteString("\n\n")

	// 3. Git context.
	gitCtx := GetGitContext(env.WorkingDirectory())
	if gitCtx != "" {
		sb.WriteString(gitCtx)
		sb.WriteString("\n\n")
	}

	// 4. Tool descriptions.
	sb.WriteString("# Available Tools\n\n")
	for _, def := range p.registry.Definitions() {
		fmt.Fprintf(&sb, "## %s\n%s\n\n", def.Name, def.Description)
	}

	// 5. Project-specific instructions.
	if projectDocs != "" {
		sb.WriteString("# Project Instructions\n\n")
		sb.WriteString(projectDocs)
		sb.WriteString("\n\n")
	}

	return sb.String()
}

// ProviderOptions returns Anthropic-specific request options.
func (p *AnthropicProfile) ProviderOptions() map[string]interface{} {
	return map[string]interface{}{
		"anthropic": map[string]interface{}{
			"beta_headers": []string{"extended-thinking-2025-04-11"},
		},
	}
}

const anthropicBasePrompt = `You are an autonomous coding agent. You help users with software engineering tasks by reading files, editing code, running commands, and iterating until the task is done.

# Core Principles

- Read files before editing them. Understand existing code before suggesting modifications.
- Prefer editing existing files over creating new ones.
- Use the edit_file tool for modifications. The old_string parameter must be an exact match of text in the file and must be unique. If old_string appears multiple times, provide more surrounding context to make it unique.
- Keep changes minimal and focused. Only make changes that are directly requested or clearly necessary.
- After making changes, verify them by reading the modified file or running relevant tests.
- When running shell commands, prefer short-running commands. Use timeouts for potentially long-running operations.

# Tool Usage Guidelines

- Use read_file to examine file contents before editing.
- Use edit_file for targeted modifications with old_string/new_string replacements.
- Use write_file only for creating entirely new files.
- Use shell for running commands, tests, and build operations.
- Use grep to search file contents by pattern.
- Use glob to find files by name pattern.

# Error Handling

- If a tool call fails, analyze the error and try a different approach.
- If edit_file fails because old_string is not found, re-read the file to get the current content.
- If edit_file fails because old_string is not unique, provide more context lines.
- If a command fails, inspect the output and fix the issue.

# Best Practices

- Write clean, idiomatic code that follows the project's existing style.
- Do not introduce security vulnerabilities.
- Do not add unnecessary dependencies.
- Test changes when possible.`
