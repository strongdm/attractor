package agentloop

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

const maxProjectDocBytes = 32 * 1024 // 32KB

// BuildEnvironmentContext generates the structured environment context block.
func BuildEnvironmentContext(env ExecutionEnvironment, model string) string {
	workingDir := env.WorkingDirectory()
	isGitRepo := isGitRepository(workingDir)
	gitBranch := ""
	if isGitRepo {
		gitBranch = getGitBranch(workingDir)
	}

	var sb strings.Builder
	sb.WriteString("<environment>\n")
	fmt.Fprintf(&sb, "Working directory: %s\n", workingDir)
	fmt.Fprintf(&sb, "Is git repository: %v\n", isGitRepo)
	if gitBranch != "" {
		fmt.Fprintf(&sb, "Git branch: %s\n", gitBranch)
	}
	fmt.Fprintf(&sb, "Platform: %s\n", env.Platform())
	fmt.Fprintf(&sb, "OS version: %s\n", env.OSVersion())
	fmt.Fprintf(&sb, "Today's date: %s\n", time.Now().Format("2006-01-02"))
	if model != "" {
		fmt.Fprintf(&sb, "Model: %s\n", model)
	}
	sb.WriteString("</environment>")
	return sb.String()
}

// DiscoverProjectDocs finds and loads project instruction files.
// It walks from the git root (or working directory) looking for recognized
// instruction files and loads them according to the provider filter.
func DiscoverProjectDocs(workingDir string, providerFilter string) string {
	root := gitRoot(workingDir)
	if root == "" {
		root = workingDir
	}

	// Determine which files to load based on provider.
	recognizedFiles := []string{"AGENTS.md"} // Always loaded.
	switch providerFilter {
	case "anthropic":
		recognizedFiles = append(recognizedFiles, "CLAUDE.md")
	case "gemini":
		recognizedFiles = append(recognizedFiles, "GEMINI.md")
	case "openai":
		recognizedFiles = append(recognizedFiles, ".codex/instructions.md")
	}

	var docs []string
	totalBytes := 0

	// Collect directories from root to working dir.
	dirs := collectPathHierarchy(root, workingDir)

	for _, dir := range dirs {
		for _, fileName := range recognizedFiles {
			path := filepath.Join(dir, fileName)
			content, err := os.ReadFile(path)
			if err != nil {
				continue
			}

			remaining := maxProjectDocBytes - totalBytes
			if remaining <= 0 {
				docs = append(docs, "[Project instructions truncated at 32KB]")
				return strings.Join(docs, "\n\n---\n\n")
			}

			text := string(content)
			if len(text) > remaining {
				text = text[:remaining] + "\n[Project instructions truncated at 32KB]"
			}

			header := fmt.Sprintf("# %s (from %s)", fileName, dir)
			docs = append(docs, header+"\n\n"+text)
			totalBytes += len(text)
		}
	}

	if len(docs) == 0 {
		return ""
	}
	return strings.Join(docs, "\n\n---\n\n")
}

// GetGitContext returns a summary of the git state for the system prompt.
func GetGitContext(workingDir string) string {
	root := gitRoot(workingDir)
	if root == "" {
		return ""
	}

	var sb strings.Builder
	sb.WriteString("<git_context>\n")

	// Current branch.
	branch := getGitBranch(root)
	if branch != "" {
		fmt.Fprintf(&sb, "Branch: %s\n", branch)
	}

	// Short status.
	status := runGitCommand(root, "status", "--short")
	if status != "" {
		lines := strings.Split(strings.TrimSpace(status), "\n")
		fmt.Fprintf(&sb, "Modified/untracked files: %d\n", len(lines))
	}

	// Recent commits.
	log := runGitCommand(root, "log", "--oneline", "-10")
	if log != "" {
		sb.WriteString("Recent commits:\n")
		sb.WriteString(log)
		sb.WriteString("\n")
	}

	sb.WriteString("</git_context>")
	return sb.String()
}

// collectPathHierarchy returns directories from root to target, inclusive.
func collectPathHierarchy(root, target string) []string {
	root = filepath.Clean(root)
	target = filepath.Clean(target)

	if root == target {
		return []string{root}
	}

	var dirs []string
	dirs = append(dirs, root)

	rel, err := filepath.Rel(root, target)
	if err != nil {
		return dirs
	}

	parts := strings.Split(rel, string(filepath.Separator))
	current := root
	for _, part := range parts {
		if part == "." {
			continue
		}
		current = filepath.Join(current, part)
		dirs = append(dirs, current)
	}
	return dirs
}

func isGitRepository(dir string) bool {
	cmd := exec.Command("git", "rev-parse", "--is-inside-work-tree")
	cmd.Dir = dir
	out, err := cmd.Output()
	return err == nil && strings.TrimSpace(string(out)) == "true"
}

func gitRoot(dir string) string {
	cmd := exec.Command("git", "rev-parse", "--show-toplevel")
	cmd.Dir = dir
	out, err := cmd.Output()
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(out))
}

func getGitBranch(dir string) string {
	cmd := exec.Command("git", "rev-parse", "--abbrev-ref", "HEAD")
	cmd.Dir = dir
	out, err := cmd.Output()
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(out))
}

func runGitCommand(dir string, args ...string) string {
	cmd := exec.Command("git", args...)
	cmd.Dir = dir
	out, err := cmd.Output()
	if err != nil {
		return ""
	}
	return string(out)
}
