package agentloop

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"time"
)

// ExecResult holds the result of a command execution.
type ExecResult struct {
	Stdout    string `json:"stdout"`
	Stderr    string `json:"stderr"`
	ExitCode  int    `json:"exit_code"`
	TimedOut  bool   `json:"timed_out"`
	DurationMs int64 `json:"duration_ms"`
}

// Output returns combined stdout and stderr.
func (r ExecResult) Output() string {
	if r.Stderr == "" {
		return r.Stdout
	}
	if r.Stdout == "" {
		return r.Stderr
	}
	return r.Stdout + "\n" + r.Stderr
}

// DirEntry represents a filesystem directory entry.
type DirEntry struct {
	Name  string `json:"name"`
	IsDir bool   `json:"is_dir"`
	Size  int64  `json:"size,omitempty"`
}

// GrepOptions configures grep behavior.
type GrepOptions struct {
	GlobFilter      string `json:"glob_filter,omitempty"`
	CaseInsensitive bool   `json:"case_insensitive,omitempty"`
	MaxResults      int    `json:"max_results,omitempty"`
}

// ExecutionEnvironment abstracts where tool operations run.
type ExecutionEnvironment interface {
	// File operations.
	ReadFile(path string, offset, limit int) (string, error)
	WriteFile(path string, content string) error
	FileExists(path string) bool
	ListDirectory(path string, depth int) ([]DirEntry, error)

	// Command execution.
	ExecCommand(ctx context.Context, command string, timeoutMs int, workingDir string, envVars map[string]string) (*ExecResult, error)

	// Search operations.
	Grep(ctx context.Context, pattern string, path string, options GrepOptions) (string, error)
	Glob(pattern string, path string) ([]string, error)

	// Lifecycle.
	Initialize() error
	Cleanup() error

	// Metadata.
	WorkingDirectory() string
	Platform() string
	OSVersion() string
}

// sensitiveEnvPatterns are case-insensitive suffixes for environment variables
// that should be excluded by default.
var sensitiveEnvPatterns = []string{
	"_API_KEY",
	"_SECRET",
	"_TOKEN",
	"_PASSWORD",
	"_CREDENTIAL",
}

// safeEnvVars are always included regardless of filtering.
var safeEnvVars = map[string]bool{
	"PATH": true, "HOME": true, "USER": true, "SHELL": true,
	"LANG": true, "TERM": true, "TMPDIR": true,
	"GOPATH": true, "GOROOT": true, "CARGO_HOME": true,
	"NVM_DIR": true, "RUSTUP_HOME": true, "PYENV_ROOT": true,
	"XDG_CONFIG_HOME": true, "XDG_DATA_HOME": true, "XDG_CACHE_HOME": true,
}

// isSensitiveEnvVar checks if a variable name matches sensitive patterns.
func isSensitiveEnvVar(name string) bool {
	upper := strings.ToUpper(name)
	for _, pattern := range sensitiveEnvPatterns {
		if strings.HasSuffix(upper, pattern) {
			return true
		}
	}
	return false
}

// filterEnvironment returns a filtered set of environment variables,
// excluding sensitive ones.
func filterEnvironment() []string {
	var filtered []string
	for _, env := range os.Environ() {
		parts := strings.SplitN(env, "=", 2)
		if len(parts) != 2 {
			continue
		}
		name := parts[0]
		if safeEnvVars[name] || !isSensitiveEnvVar(name) {
			filtered = append(filtered, env)
		}
	}
	return filtered
}

// LocalExecutionEnvironment runs tools on the local machine.
type LocalExecutionEnvironment struct {
	workingDir string
	platform   string
	osVersion  string
}

// NewLocalExecutionEnvironment creates a local execution environment.
func NewLocalExecutionEnvironment(workingDir string) *LocalExecutionEnvironment {
	if workingDir == "" {
		workingDir, _ = os.Getwd()
	}
	return &LocalExecutionEnvironment{
		workingDir: workingDir,
		platform:   runtime.GOOS,
		osVersion:  runtime.GOOS + "/" + runtime.GOARCH,
	}
}

func (e *LocalExecutionEnvironment) Initialize() error {
	return os.MkdirAll(e.workingDir, 0755)
}

func (e *LocalExecutionEnvironment) Cleanup() error {
	return nil
}

func (e *LocalExecutionEnvironment) WorkingDirectory() string {
	return e.workingDir
}

func (e *LocalExecutionEnvironment) Platform() string {
	return e.platform
}

func (e *LocalExecutionEnvironment) OSVersion() string {
	return e.osVersion
}

func (e *LocalExecutionEnvironment) resolvePath(path string) string {
	if filepath.IsAbs(path) {
		return path
	}
	return filepath.Join(e.workingDir, path)
}

func (e *LocalExecutionEnvironment) ReadFile(path string, offset, limit int) (string, error) {
	resolved := e.resolvePath(path)
	data, err := os.ReadFile(resolved)
	if err != nil {
		return "", fmt.Errorf("read_file: %w", err)
	}

	lines := strings.Split(string(data), "\n")

	// Apply offset (1-based).
	startLine := 0
	if offset > 0 {
		startLine = offset - 1
	}
	if startLine >= len(lines) {
		return "", nil
	}

	// Apply limit.
	endLine := len(lines)
	if limit > 0 && startLine+limit < endLine {
		endLine = startLine + limit
	}

	// Format with line numbers.
	var sb strings.Builder
	for i := startLine; i < endLine; i++ {
		fmt.Fprintf(&sb, "%d | %s\n", i+1, lines[i])
	}
	return sb.String(), nil
}

func (e *LocalExecutionEnvironment) WriteFile(path string, content string) error {
	resolved := e.resolvePath(path)
	dir := filepath.Dir(resolved)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("write_file: failed to create directory: %w", err)
	}
	return os.WriteFile(resolved, []byte(content), 0644)
}

func (e *LocalExecutionEnvironment) FileExists(path string) bool {
	resolved := e.resolvePath(path)
	_, err := os.Stat(resolved)
	return err == nil
}

func (e *LocalExecutionEnvironment) ListDirectory(path string, depth int) ([]DirEntry, error) {
	resolved := e.resolvePath(path)
	entries, err := os.ReadDir(resolved)
	if err != nil {
		return nil, fmt.Errorf("list_directory: %w", err)
	}

	var result []DirEntry
	for _, entry := range entries {
		de := DirEntry{
			Name:  entry.Name(),
			IsDir: entry.IsDir(),
		}
		if info, err := entry.Info(); err == nil {
			de.Size = info.Size()
		}
		result = append(result, de)
	}
	return result, nil
}

func (e *LocalExecutionEnvironment) ExecCommand(ctx context.Context, command string, timeoutMs int, workingDir string, envVars map[string]string) (*ExecResult, error) {
	if workingDir == "" {
		workingDir = e.workingDir
	} else {
		workingDir = e.resolvePath(workingDir)
	}

	// Create context with timeout.
	if timeoutMs > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, time.Duration(timeoutMs)*time.Millisecond)
		defer cancel()
	}

	// Determine shell.
	shell := "/bin/bash"
	shellArg := "-c"
	if runtime.GOOS == "windows" {
		shell = "cmd.exe"
		shellArg = "/c"
	}

	cmd := exec.CommandContext(ctx, shell, shellArg, command)
	cmd.Dir = workingDir

	// Set up process group for clean killability.
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}

	// Filtered environment + any caller-specified overrides.
	env := filterEnvironment()
	for k, v := range envVars {
		env = append(env, k+"="+v)
	}
	cmd.Env = env

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	start := time.Now()
	err := cmd.Run()
	duration := time.Since(start)

	result := &ExecResult{
		Stdout:     stdout.String(),
		Stderr:     stderr.String(),
		DurationMs: duration.Milliseconds(),
	}

	if err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			result.TimedOut = true
			result.ExitCode = -1
			// Attempt to kill the process group.
			if cmd.Process != nil {
				_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
			}
		} else if exitErr, ok := err.(*exec.ExitError); ok {
			result.ExitCode = exitErr.ExitCode()
		} else {
			return nil, fmt.Errorf("exec_command: %w", err)
		}
	}

	return result, nil
}

func (e *LocalExecutionEnvironment) Grep(ctx context.Context, pattern string, path string, options GrepOptions) (string, error) {
	if path == "" {
		path = e.workingDir
	} else {
		path = e.resolvePath(path)
	}

	// Try ripgrep first, fall back to grep.
	rgPath, err := exec.LookPath("rg")
	if err != nil {
		return e.grepFallback(ctx, pattern, path, options)
	}

	args := []string{pattern, path, "--line-number", "--no-heading"}
	if options.CaseInsensitive {
		args = append(args, "-i")
	}
	if options.GlobFilter != "" {
		args = append(args, "--glob", options.GlobFilter)
	}
	if options.MaxResults > 0 {
		args = append(args, "--max-count", fmt.Sprintf("%d", options.MaxResults))
	}

	cmd := exec.CommandContext(ctx, rgPath, args...)
	cmd.Dir = e.workingDir
	var stdout bytes.Buffer
	cmd.Stdout = &stdout
	_ = cmd.Run() // rg returns exit 1 for no matches, which is fine.
	return stdout.String(), nil
}

func (e *LocalExecutionEnvironment) grepFallback(ctx context.Context, pattern string, path string, options GrepOptions) (string, error) {
	args := []string{"-rn", pattern, path}
	if options.CaseInsensitive {
		args = append([]string{"-i"}, args...)
	}

	cmd := exec.CommandContext(ctx, "grep", args...)
	cmd.Dir = e.workingDir
	var stdout bytes.Buffer
	cmd.Stdout = &stdout
	_ = cmd.Run()
	return stdout.String(), nil
}

func (e *LocalExecutionEnvironment) Glob(pattern string, path string) ([]string, error) {
	if path == "" {
		path = e.workingDir
	} else {
		path = e.resolvePath(path)
	}

	fullPattern := filepath.Join(path, pattern)
	matches, err := filepath.Glob(fullPattern)
	if err != nil {
		return nil, fmt.Errorf("glob: %w", err)
	}

	// Make paths relative to working dir if possible.
	result := make([]string, len(matches))
	for i, m := range matches {
		rel, err := filepath.Rel(e.workingDir, m)
		if err != nil {
			result[i] = m
		} else {
			result[i] = rel
		}
	}
	return result, nil
}
