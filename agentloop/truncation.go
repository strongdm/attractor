package agentloop

import (
	"fmt"
	"strings"
)

// TruncationMode specifies how output is truncated.
type TruncationMode string

const (
	TruncateHeadTail TruncationMode = "head_tail"
	TruncateTail     TruncationMode = "tail"
)

// Default character limits per tool (Section 5.2).
var DefaultToolCharLimits = map[string]int{
	"read_file":   50000,
	"shell":       30000,
	"grep":        20000,
	"glob":        20000,
	"edit_file":   10000,
	"apply_patch": 10000,
	"write_file":  1000,
	"spawn_agent": 20000,
}

// Default truncation modes per tool.
var DefaultTruncationModes = map[string]TruncationMode{
	"read_file":   TruncateHeadTail,
	"shell":       TruncateHeadTail,
	"grep":        TruncateTail,
	"glob":        TruncateTail,
	"edit_file":   TruncateTail,
	"apply_patch": TruncateTail,
	"write_file":  TruncateTail,
	"spawn_agent": TruncateHeadTail,
}

// Default line limits per tool (applied after character truncation).
var DefaultToolLineLimits = map[string]int{
	"shell": 256,
	"grep":  200,
	"glob":  500,
}

// TruncateOutput applies character-based truncation to output.
func TruncateOutput(output string, maxChars int, mode TruncationMode) string {
	if len(output) <= maxChars {
		return output
	}

	switch mode {
	case TruncateHeadTail:
		half := maxChars / 2
		removed := len(output) - maxChars
		return output[:half] +
			fmt.Sprintf("\n\n[WARNING: Tool output was truncated. %d characters were removed from the middle. "+
				"The full output is available in the event stream. "+
				"If you need to see specific parts, re-run the tool with more targeted parameters.]\n\n",
				removed) +
			output[len(output)-half:]

	case TruncateTail:
		removed := len(output) - maxChars
		return fmt.Sprintf("[WARNING: Tool output was truncated. First %d characters were removed. "+
			"The full output is available in the event stream.]\n\n",
			removed) +
			output[len(output)-maxChars:]

	default:
		// Default to head_tail.
		half := maxChars / 2
		removed := len(output) - maxChars
		return output[:half] +
			fmt.Sprintf("\n\n[WARNING: Tool output was truncated. %d characters were removed from the middle.]\n\n",
				removed) +
			output[len(output)-half:]
	}
}

// TruncateLines applies line-based truncation using head/tail split.
func TruncateLines(output string, maxLines int) string {
	lines := strings.Split(output, "\n")
	if len(lines) <= maxLines {
		return output
	}

	headCount := maxLines / 2
	tailCount := maxLines - headCount
	omitted := len(lines) - headCount - tailCount

	return strings.Join(lines[:headCount], "\n") +
		fmt.Sprintf("\n[... %d lines omitted ...]\n", omitted) +
		strings.Join(lines[len(lines)-tailCount:], "\n")
}

// TruncateToolOutput applies the full truncation pipeline for a tool:
// 1. Character-based truncation (primary, handles pathological cases)
// 2. Line-based truncation (secondary, for readability)
func TruncateToolOutput(output string, toolName string, charLimits map[string]int, lineLimits map[string]int) string {
	// Step 1: Character-based truncation.
	maxChars, ok := charLimits[toolName]
	if !ok {
		maxChars, ok = DefaultToolCharLimits[toolName]
		if !ok {
			maxChars = 30000 // fallback default
		}
	}

	mode, ok := DefaultTruncationModes[toolName]
	if !ok {
		mode = TruncateHeadTail
	}

	result := TruncateOutput(output, maxChars, mode)

	// Step 2: Line-based truncation.
	maxLines := 0
	if lineLimits != nil {
		if ml, ok := lineLimits[toolName]; ok {
			maxLines = ml
		}
	}
	if maxLines == 0 {
		if ml, ok := DefaultToolLineLimits[toolName]; ok {
			maxLines = ml
		}
	}
	if maxLines > 0 {
		result = TruncateLines(result, maxLines)
	}

	return result
}
