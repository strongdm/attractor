package agentloop

import (
	"fmt"
	"strings"
)

// OpenAIProfile provides codex-rs-aligned tools and system prompts
// for OpenAI models (GPT-5.2, GPT-5.2-codex, etc.).
type OpenAIProfile struct {
	BaseProfile
}

// NewOpenAIProfile creates a profile for OpenAI models.
func NewOpenAIProfile(model string) *OpenAIProfile {
	p := &OpenAIProfile{
		BaseProfile: BaseProfile{
			providerID:                "openai",
			model:                     model,
			registry:                  NewToolRegistry(),
			supportsReasoning:         true,
			supportsStreaming:          true,
			supportsParallelToolCalls: true,
			contextWindowSize:         1047576,
		},
	}

	// Register codex-rs-aligned core tools.
	// OpenAI uses apply_patch as the primary editing tool (v4a format).
	RegisterCoreTools(p.registry, 10000, 600000) // 10s default timeout per codex-rs convention.

	// Add apply_patch (the native OpenAI editing format).
	RegisterApplyPatch(p.registry)

	return p
}

// BuildSystemPrompt constructs the OpenAI/codex-rs-aligned system prompt.
func (p *OpenAIProfile) BuildSystemPrompt(env ExecutionEnvironment, projectDocs string) string {
	var sb strings.Builder

	// 1. Provider-specific base instructions (codex-rs-aligned).
	sb.WriteString(openaiBasePrompt)
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

// ProviderOptions returns OpenAI-specific request options.
func (p *OpenAIProfile) ProviderOptions() map[string]interface{} {
	return nil
}

const openaiBasePrompt = `You are an autonomous coding agent. You help users with software engineering tasks by reading files, editing code, running commands, and iterating until the task is done.

# Core Principles

- Read files before editing them. Understand existing code before suggesting modifications.
- Use apply_patch for all file modifications. The patch format uses context lines to locate changes precisely.
- Use write_file for creating entirely new files.
- Keep changes minimal and focused. Only make changes that are directly requested or clearly necessary.
- After making changes, verify them by reading the modified file or running relevant tests.

# apply_patch Format

Use the v4a patch format for all file edits:

` + "```" + `
*** Begin Patch
*** Update File: path/to/file.py
@@ context_hint
 context line (space prefix = unchanged)
-line to remove (minus prefix)
+line to add (plus prefix)
*** End Patch
` + "```" + `

Key rules:
- Space prefix for context lines (unchanged)
- Minus prefix for lines to delete
- Plus prefix for lines to add
- Include ~3 lines of context above and below each change
- The @@ line provides a context hint to locate the change

# Tool Usage Guidelines

- Use read_file to examine file contents before editing.
- Use apply_patch for all modifications to existing files.
- Use write_file only for creating entirely new files.
- Use shell for running commands (10s default timeout).
- Use grep to search file contents by pattern.
- Use glob to find files by name pattern.

# Error Handling

- If a tool call fails, analyze the error and try a different approach.
- If apply_patch fails, re-read the file to get fresh context.
- If a command fails, inspect the output and fix the issue.

# Best Practices

- Write clean, idiomatic code that follows the project's existing style.
- Do not introduce security vulnerabilities.
- Do not add unnecessary dependencies.
- Test changes when possible.`
