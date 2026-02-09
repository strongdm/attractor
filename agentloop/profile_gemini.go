package agentloop

import (
	"fmt"
	"strings"
)

// GeminiProfile provides gemini-cli-aligned tools and system prompts
// for Gemini models (Gemini 3 Pro, Flash, etc.).
type GeminiProfile struct {
	BaseProfile
}

// NewGeminiProfile creates a profile for Gemini models.
func NewGeminiProfile(model string) *GeminiProfile {
	p := &GeminiProfile{
		BaseProfile: BaseProfile{
			providerID:                "gemini",
			model:                     model,
			registry:                  NewToolRegistry(),
			supportsReasoning:         true,
			supportsStreaming:          true,
			supportsParallelToolCalls: true,
			contextWindowSize:         1048576,
		},
	}

	// Register gemini-cli-aligned core tools.
	RegisterCoreTools(p.registry, 10000, 600000) // 10s default timeout per gemini-cli convention.

	return p
}

// BuildSystemPrompt constructs the Gemini/gemini-cli-aligned system prompt.
func (p *GeminiProfile) BuildSystemPrompt(env ExecutionEnvironment, projectDocs string) string {
	var sb strings.Builder

	// 1. Provider-specific base instructions (gemini-cli-aligned).
	sb.WriteString(geminiBasePrompt)
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

// ProviderOptions returns Gemini-specific request options.
func (p *GeminiProfile) ProviderOptions() map[string]interface{} {
	return map[string]interface{}{
		"gemini": map[string]interface{}{
			"safety_settings": "default",
		},
	}
}

const geminiBasePrompt = `You are an autonomous coding agent. You help users with software engineering tasks by reading files, editing code, running commands, and iterating until the task is done.

# Core Principles

- Read files before editing them. Understand existing code before suggesting modifications.
- Use edit_file for targeted modifications with search-and-replace.
- Use write_file for creating new files.
- Keep changes minimal and focused. Only make changes that are directly requested or clearly necessary.
- After making changes, verify them by reading the modified file or running relevant tests.

# Tool Usage Guidelines

- Use read_file to examine file contents before editing.
- Use edit_file for modifications with old_string/new_string search-and-replace.
- Use write_file for creating entirely new files.
- Use shell for running commands (10s default timeout).
- Use grep to search file contents by pattern.
- Use glob to find files by name pattern.

# GEMINI.md

If the project contains a GEMINI.md file, follow the instructions in it. GEMINI.md files in subdirectories take precedence over root-level files.

# Error Handling

- If a tool call fails, analyze the error and try a different approach.
- If edit_file fails, re-read the file to get current content.
- If a command fails, inspect the output and fix the issue.

# Best Practices

- Write clean, idiomatic code that follows the project's existing style.
- Do not introduce security vulnerabilities.
- Do not add unnecessary dependencies.
- Test changes when possible.`
