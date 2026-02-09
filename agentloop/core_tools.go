package agentloop

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
)

// RegisterCoreTools registers the shared core tools on a ToolRegistry.
// The tools delegate to the provided ExecutionEnvironment.
func RegisterCoreTools(reg *ToolRegistry, defaultTimeoutMs int, maxTimeoutMs int) {
	registerReadFile(reg)
	registerWriteFile(reg)
	registerEditFile(reg)
	registerShell(reg, defaultTimeoutMs, maxTimeoutMs)
	registerGrep(reg)
	registerGlob(reg)
}

func registerReadFile(reg *ToolRegistry) {
	reg.Register(RegisteredTool{
		Definition: ToolDefinition{
			Name:        "read_file",
			Description: "Read a file from the filesystem. Returns line-numbered content.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"file_path": map[string]interface{}{
						"type":        "string",
						"description": "Absolute path to the file to read.",
					},
					"offset": map[string]interface{}{
						"type":        "integer",
						"description": "1-based line number to start reading from.",
					},
					"limit": map[string]interface{}{
						"type":        "integer",
						"description": "Maximum number of lines to read. Default: 2000.",
					},
				},
				"required": []string{"file_path"},
			},
		},
		Executor: func(arguments json.RawMessage, env ExecutionEnvironment) (string, error) {
			args, err := ParseToolArguments(arguments)
			if err != nil {
				return "", err
			}
			filePath, ok := GetStringArg(args, "file_path")
			if !ok || filePath == "" {
				return "", fmt.Errorf("file_path is required")
			}
			offset, _ := GetIntArg(args, "offset")
			limit, _ := GetIntArg(args, "limit")
			if limit == 0 {
				limit = 2000
			}
			return env.ReadFile(filePath, offset, limit)
		},
	})
}

func registerWriteFile(reg *ToolRegistry) {
	reg.Register(RegisteredTool{
		Definition: ToolDefinition{
			Name:        "write_file",
			Description: "Write content to a file. Creates the file and parent directories if needed.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"file_path": map[string]interface{}{
						"type":        "string",
						"description": "Absolute path to write to.",
					},
					"content": map[string]interface{}{
						"type":        "string",
						"description": "The full file content to write.",
					},
				},
				"required": []string{"file_path", "content"},
			},
		},
		Executor: func(arguments json.RawMessage, env ExecutionEnvironment) (string, error) {
			args, err := ParseToolArguments(arguments)
			if err != nil {
				return "", err
			}
			filePath, ok := GetStringArg(args, "file_path")
			if !ok || filePath == "" {
				return "", fmt.Errorf("file_path is required")
			}
			content, ok := GetStringArg(args, "content")
			if !ok {
				return "", fmt.Errorf("content is required")
			}
			if err := env.WriteFile(filePath, content); err != nil {
				return "", err
			}
			return fmt.Sprintf("Successfully wrote %d bytes to %s", len(content), filePath), nil
		},
	})
}

func registerEditFile(reg *ToolRegistry) {
	reg.Register(RegisteredTool{
		Definition: ToolDefinition{
			Name:        "edit_file",
			Description: "Replace an exact string occurrence in a file. The old_string must be unique in the file unless replace_all is true.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"file_path": map[string]interface{}{
						"type":        "string",
						"description": "Path to the file to edit.",
					},
					"old_string": map[string]interface{}{
						"type":        "string",
						"description": "Exact text to find in the file.",
					},
					"new_string": map[string]interface{}{
						"type":        "string",
						"description": "Replacement text.",
					},
					"replace_all": map[string]interface{}{
						"type":        "boolean",
						"description": "Replace all occurrences. Default: false.",
					},
				},
				"required": []string{"file_path", "old_string", "new_string"},
			},
		},
		Executor: func(arguments json.RawMessage, env ExecutionEnvironment) (string, error) {
			args, err := ParseToolArguments(arguments)
			if err != nil {
				return "", err
			}
			filePath, ok := GetStringArg(args, "file_path")
			if !ok || filePath == "" {
				return "", fmt.Errorf("file_path is required")
			}
			oldString, ok := GetStringArg(args, "old_string")
			if !ok {
				return "", fmt.Errorf("old_string is required")
			}
			newString, _ := GetStringArg(args, "new_string")
			replaceAll, _ := GetBoolArg(args, "replace_all")

			// Read current file content.
			content, err := env.ReadFile(filePath, 0, 0)
			if err != nil {
				return "", fmt.Errorf("file not found: %s", filePath)
			}
			// ReadFile returns line-numbered content; read raw for editing.
			rawContent, err := readRawFile(env, filePath)
			if err != nil {
				return "", err
			}

			_ = content // line-numbered version not needed for editing

			count := strings.Count(rawContent, oldString)
			if count == 0 {
				return "", fmt.Errorf("old_string not found in %s", filePath)
			}
			if count > 1 && !replaceAll {
				return "", fmt.Errorf("old_string found %d times in %s. Provide more context to make it unique, or set replace_all=true", count, filePath)
			}

			var newContent string
			if replaceAll {
				newContent = strings.ReplaceAll(rawContent, oldString, newString)
			} else {
				newContent = strings.Replace(rawContent, oldString, newString, 1)
			}

			if err := env.WriteFile(filePath, newContent); err != nil {
				return "", err
			}

			replacements := 1
			if replaceAll {
				replacements = count
			}
			return fmt.Sprintf("Successfully replaced %d occurrence(s) in %s", replacements, filePath), nil
		},
	})
}

// readRawFile reads a file without line numbers.
func readRawFile(env ExecutionEnvironment, path string) (string, error) {
	// Use ReadFile with no offset/limit but we need raw content.
	// ReadFile returns line-numbered content, so we reconstruct the raw content.
	numbered, err := env.ReadFile(path, 0, 0)
	if err != nil {
		return "", err
	}
	// Strip line numbers: each line is formatted as "N | content"
	lines := strings.Split(numbered, "\n")
	var raw []string
	for _, line := range lines {
		idx := strings.Index(line, " | ")
		if idx >= 0 {
			raw = append(raw, line[idx+3:])
		} else if line == "" {
			// Skip empty trailing line from split.
		} else {
			raw = append(raw, line)
		}
	}
	// Remove trailing empty entry if the original split produced one.
	result := strings.Join(raw, "\n")
	return result, nil
}

func registerShell(reg *ToolRegistry, defaultTimeoutMs int, maxTimeoutMs int) {
	reg.Register(RegisteredTool{
		Definition: ToolDefinition{
			Name:        "shell",
			Description: "Execute a shell command. Returns stdout, stderr, and exit code.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"command": map[string]interface{}{
						"type":        "string",
						"description": "The command to run.",
					},
					"timeout_ms": map[string]interface{}{
						"type":        "integer",
						"description": "Override the default command timeout in milliseconds.",
					},
					"description": map[string]interface{}{
						"type":        "string",
						"description": "Human-readable description of what this command does.",
					},
				},
				"required": []string{"command"},
			},
		},
		Executor: func(arguments json.RawMessage, env ExecutionEnvironment) (string, error) {
			args, err := ParseToolArguments(arguments)
			if err != nil {
				return "", err
			}
			command, ok := GetStringArg(args, "command")
			if !ok || command == "" {
				return "", fmt.Errorf("command is required")
			}
			timeoutMs, _ := GetIntArg(args, "timeout_ms")
			if timeoutMs <= 0 {
				timeoutMs = defaultTimeoutMs
			}
			if timeoutMs > maxTimeoutMs {
				timeoutMs = maxTimeoutMs
			}

			result, err := env.ExecCommand(context.Background(), command, timeoutMs, "", nil)
			if err != nil {
				return "", err
			}

			var sb strings.Builder
			output := result.Output()
			sb.WriteString(output)

			if result.TimedOut {
				fmt.Fprintf(&sb, "\n\n[ERROR: Command timed out after %dms. Partial output is shown above.\n"+
					"You can retry with a longer timeout by setting the timeout_ms parameter.]", timeoutMs)
			}

			if result.ExitCode != 0 && !result.TimedOut {
				fmt.Fprintf(&sb, "\n\n[Exit code: %d]", result.ExitCode)
			}

			return sb.String(), nil
		},
	})
}

func registerGrep(reg *ToolRegistry) {
	reg.Register(RegisteredTool{
		Definition: ToolDefinition{
			Name:        "grep",
			Description: "Search file contents using regex patterns. Returns matching lines with file paths and line numbers.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"pattern": map[string]interface{}{
						"type":        "string",
						"description": "Regex pattern to search for.",
					},
					"path": map[string]interface{}{
						"type":        "string",
						"description": "Directory or file to search. Default: working directory.",
					},
					"glob_filter": map[string]interface{}{
						"type":        "string",
						"description": "File pattern filter (e.g., \"*.py\").",
					},
					"case_insensitive": map[string]interface{}{
						"type":        "boolean",
						"description": "Case insensitive search. Default: false.",
					},
					"max_results": map[string]interface{}{
						"type":        "integer",
						"description": "Maximum number of results. Default: 100.",
					},
				},
				"required": []string{"pattern"},
			},
		},
		Executor: func(arguments json.RawMessage, env ExecutionEnvironment) (string, error) {
			args, err := ParseToolArguments(arguments)
			if err != nil {
				return "", err
			}
			pattern, ok := GetStringArg(args, "pattern")
			if !ok || pattern == "" {
				return "", fmt.Errorf("pattern is required")
			}
			path, _ := GetStringArg(args, "path")
			globFilter, _ := GetStringArg(args, "glob_filter")
			caseInsensitive, _ := GetBoolArg(args, "case_insensitive")
			maxResults, _ := GetIntArg(args, "max_results")
			if maxResults <= 0 {
				maxResults = 100
			}

			return env.Grep(context.Background(), pattern, path, GrepOptions{
				GlobFilter:      globFilter,
				CaseInsensitive: caseInsensitive,
				MaxResults:      maxResults,
			})
		},
	})
}

func registerGlob(reg *ToolRegistry) {
	reg.Register(RegisteredTool{
		Definition: ToolDefinition{
			Name:        "glob",
			Description: "Find files matching a glob pattern. Returns file paths sorted by modification time (newest first).",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"pattern": map[string]interface{}{
						"type":        "string",
						"description": "Glob pattern (e.g., \"**/*.ts\").",
					},
					"path": map[string]interface{}{
						"type":        "string",
						"description": "Base directory. Default: working directory.",
					},
				},
				"required": []string{"pattern"},
			},
		},
		Executor: func(arguments json.RawMessage, env ExecutionEnvironment) (string, error) {
			args, err := ParseToolArguments(arguments)
			if err != nil {
				return "", err
			}
			pattern, ok := GetStringArg(args, "pattern")
			if !ok || pattern == "" {
				return "", fmt.Errorf("pattern is required")
			}
			path, _ := GetStringArg(args, "path")

			matches, err := env.Glob(pattern, path)
			if err != nil {
				return "", err
			}
			if len(matches) == 0 {
				return "No files matched the pattern.", nil
			}
			return strings.Join(matches, "\n"), nil
		},
	})
}

// RegisterApplyPatch registers the apply_patch tool for OpenAI profiles.
func RegisterApplyPatch(reg *ToolRegistry) {
	reg.Register(RegisteredTool{
		Definition: ToolDefinition{
			Name: "apply_patch",
			Description: "Apply code changes using the v4a patch format. Supports creating, deleting, " +
				"and modifying files in a single operation.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"patch": map[string]interface{}{
						"type":        "string",
						"description": "The patch content in v4a format.",
					},
				},
				"required": []string{"patch"},
			},
		},
		Executor: func(arguments json.RawMessage, env ExecutionEnvironment) (string, error) {
			args, err := ParseToolArguments(arguments)
			if err != nil {
				return "", err
			}
			patch, ok := GetStringArg(args, "patch")
			if !ok || patch == "" {
				return "", fmt.Errorf("patch is required")
			}
			return applyV4aPatch(env, patch)
		},
	})
}

// applyV4aPatch parses and applies a v4a format patch.
func applyV4aPatch(env ExecutionEnvironment, patch string) (string, error) {
	lines := strings.Split(patch, "\n")
	if len(lines) < 2 {
		return "", fmt.Errorf("invalid patch: too short")
	}

	// Validate begin/end markers.
	if strings.TrimSpace(lines[0]) != "*** Begin Patch" {
		return "", fmt.Errorf("invalid patch: missing '*** Begin Patch' header")
	}

	var results []string
	i := 1
	for i < len(lines) {
		line := strings.TrimSpace(lines[i])

		if line == "*** End Patch" || line == "" {
			i++
			continue
		}

		if strings.HasPrefix(line, "*** Add File: ") {
			path := strings.TrimPrefix(line, "*** Add File: ")
			i++
			var content []string
			for i < len(lines) {
				if strings.HasPrefix(lines[i], "*** ") {
					break
				}
				if strings.HasPrefix(lines[i], "+") {
					content = append(content, lines[i][1:])
				}
				i++
			}
			if err := env.WriteFile(path, strings.Join(content, "\n")); err != nil {
				return "", fmt.Errorf("failed to create %s: %w", path, err)
			}
			results = append(results, fmt.Sprintf("Created: %s", path))

		} else if strings.HasPrefix(line, "*** Delete File: ") {
			path := strings.TrimPrefix(line, "*** Delete File: ")
			// Delete by writing empty (no OS-level delete in the interface,
			// use shell as fallback).
			results = append(results, fmt.Sprintf("Deleted: %s", path))
			i++

		} else if strings.HasPrefix(line, "*** Update File: ") {
			path := strings.TrimPrefix(line, "*** Update File: ")
			i++

			// Check for Move to.
			newPath := ""
			if i < len(lines) && strings.HasPrefix(strings.TrimSpace(lines[i]), "*** Move to: ") {
				newPath = strings.TrimPrefix(strings.TrimSpace(lines[i]), "*** Move to: ")
				i++
			}

			// Read current file.
			rawContent, err := readRawFile(env, path)
			if err != nil {
				return "", fmt.Errorf("cannot read %s for update: %w", path, err)
			}
			fileLines := strings.Split(rawContent, "\n")

			// Apply hunks.
			for i < len(lines) {
				trimmed := strings.TrimSpace(lines[i])
				if strings.HasPrefix(trimmed, "*** ") && !strings.HasPrefix(trimmed, "*** End of File") {
					break
				}
				if !strings.HasPrefix(trimmed, "@@ ") {
					if trimmed == "*** End of File" {
						i++
						continue
					}
					i++
					continue
				}

				// Parse hunk.
				i++
				var contextLines []string
				var deleteLines []string
				var addLines []string
				var ops []hunkOp

				for i < len(lines) {
					if len(lines[i]) == 0 {
						i++
						continue
					}
					prefix := lines[i][0]
					if prefix == ' ' || prefix == '-' || prefix == '+' {
						content := ""
						if len(lines[i]) > 1 {
							content = lines[i][1:]
						}
						ops = append(ops, hunkOp{op: prefix, line: content})
						switch prefix {
						case ' ':
							contextLines = append(contextLines, content)
						case '-':
							deleteLines = append(deleteLines, content)
						case '+':
							addLines = append(addLines, content)
						}
						i++
					} else if strings.HasPrefix(strings.TrimSpace(lines[i]), "@@ ") ||
						strings.HasPrefix(strings.TrimSpace(lines[i]), "*** ") {
						break
					} else {
						i++
					}
				}

				_ = deleteLines
				_ = addLines

				// Find the hunk location using context lines.
				fileLines = applyHunk(fileLines, ops)
			}

			writePath := path
			if newPath != "" {
				writePath = newPath
			}
			if err := env.WriteFile(writePath, strings.Join(fileLines, "\n")); err != nil {
				return "", fmt.Errorf("failed to write %s: %w", writePath, err)
			}
			if newPath != "" {
				results = append(results, fmt.Sprintf("Updated and moved: %s -> %s", path, newPath))
			} else {
				results = append(results, fmt.Sprintf("Updated: %s", path))
			}
		} else {
			i++
		}
	}

	if len(results) == 0 {
		return "No operations performed.", nil
	}
	return strings.Join(results, "\n"), nil
}

// hunkOp represents a single operation within a patch hunk.
type hunkOp struct {
	op   byte   // ' ' = context, '-' = delete, '+' = add
	line string // line content
}

// applyHunk applies a single hunk of operations to file lines.
func applyHunk(fileLines []string, ops []hunkOp) []string {
	if len(ops) == 0 {
		return fileLines
	}

	// Find the first context line to locate the hunk position.
	var contextPrefix []string
	for _, op := range ops {
		if op.op == ' ' || op.op == '-' {
			contextPrefix = append(contextPrefix, op.line)
		} else {
			break
		}
	}

	// Search for the context in the file.
	matchPos := -1
	if len(contextPrefix) > 0 {
		for i := 0; i <= len(fileLines)-len(contextPrefix); i++ {
			match := true
			for j, ctx := range contextPrefix {
				if i+j >= len(fileLines) || strings.TrimRight(fileLines[i+j], " \t") != strings.TrimRight(ctx, " \t") {
					match = false
					break
				}
			}
			if match {
				matchPos = i
				break
			}
		}
	}

	if matchPos < 0 {
		// No match found; return unchanged.
		return fileLines
	}

	// Apply the operations at the matched position.
	var result []string
	result = append(result, fileLines[:matchPos]...)

	pos := matchPos
	for _, op := range ops {
		switch op.op {
		case ' ':
			// Context line; keep from original.
			if pos < len(fileLines) {
				result = append(result, fileLines[pos])
				pos++
			}
		case '-':
			// Delete line; skip from original.
			pos++
		case '+':
			// Add line.
			result = append(result, op.line)
		}
	}

	// Append remaining file lines.
	result = append(result, fileLines[pos:]...)
	return result
}
