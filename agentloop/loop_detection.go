package agentloop

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
)

// toolCallSignature computes a deterministic signature for a tool call
// (name + hash of arguments).
func toolCallSignature(name string, arguments json.RawMessage) string {
	h := sha256.Sum256(arguments)
	return fmt.Sprintf("%s:%x", name, h[:8])
}

// extractToolCallSignatures extracts signatures from the most recent tool
// calls in the history.
func extractToolCallSignatures(history []Turn, count int) []string {
	var sigs []string
	// Walk history backwards to find tool call signatures.
	for i := len(history) - 1; i >= 0 && len(sigs) < count; i-- {
		turn := history[i]
		if turn.Kind == TurnAssistant && turn.Assistant != nil {
			for j := len(turn.Assistant.ToolCalls) - 1; j >= 0 && len(sigs) < count; j-- {
				tc := turn.Assistant.ToolCalls[j]
				sigs = append(sigs, toolCallSignature(tc.Name, tc.Arguments))
			}
		}
	}
	// Reverse to chronological order.
	for i, j := 0, len(sigs)-1; i < j; i, j = i+1, j-1 {
		sigs[i], sigs[j] = sigs[j], sigs[i]
	}
	return sigs
}

// DetectLoop checks if the last windowSize tool calls follow a repeating
// pattern of length 1, 2, or 3.
func DetectLoop(history []Turn, windowSize int) bool {
	sigs := extractToolCallSignatures(history, windowSize)
	if len(sigs) < windowSize {
		return false
	}

	// Check for repeating patterns of length 1, 2, or 3.
	for patternLen := 1; patternLen <= 3; patternLen++ {
		if windowSize%patternLen != 0 {
			continue
		}
		pattern := sigs[:patternLen]
		allMatch := true
		for i := patternLen; i < windowSize; i += patternLen {
			for j := 0; j < patternLen; j++ {
				if sigs[i+j] != pattern[j] {
					allMatch = false
					break
				}
			}
			if !allMatch {
				break
			}
		}
		if allMatch {
			return true
		}
	}

	return false
}
