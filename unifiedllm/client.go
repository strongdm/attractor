package unifiedllm

import (
	"context"
	"fmt"
	"sync"
)

// Middleware wraps a provider call. It receives the request and a next function
// that calls the downstream handler, and returns the response.
type Middleware func(ctx context.Context, req Request, next func(context.Context, Request) (*Response, error)) (*Response, error)

// StreamMiddleware wraps a streaming provider call.
type StreamMiddleware func(ctx context.Context, req Request, next func(context.Context, Request) (<-chan StreamEvent, error)) (<-chan StreamEvent, error)

// Client is the core orchestration layer. It holds registered provider adapters,
// routes requests by provider identifier, and applies middleware.
type Client struct {
	providers       map[string]ProviderAdapter
	defaultProvider string
	middleware      []Middleware
	streamMW       []StreamMiddleware
	mu             sync.RWMutex
}

// ClientOption configures a Client.
type ClientOption func(*Client)

// WithProvider registers a provider adapter.
func WithProvider(name string, adapter ProviderAdapter) ClientOption {
	return func(c *Client) {
		c.providers[name] = adapter
	}
}

// WithDefaultProvider sets the default provider name.
func WithDefaultProvider(name string) ClientOption {
	return func(c *Client) {
		c.defaultProvider = name
	}
}

// WithMiddleware adds middleware to the client.
func WithMiddleware(mw ...Middleware) ClientOption {
	return func(c *Client) {
		c.middleware = append(c.middleware, mw...)
	}
}

// WithStreamMiddleware adds stream middleware to the client.
func WithStreamMiddleware(mw ...StreamMiddleware) ClientOption {
	return func(c *Client) {
		c.streamMW = append(c.streamMW, mw...)
	}
}

// NewClient creates a new Client with the given options.
func NewClient(opts ...ClientOption) *Client {
	c := &Client{
		providers: make(map[string]ProviderAdapter),
	}
	for _, opt := range opts {
		opt(c)
	}
	// If no default and exactly one provider, use it.
	if c.defaultProvider == "" && len(c.providers) == 1 {
		for name := range c.providers {
			c.defaultProvider = name
		}
	}
	return c
}

// RegisterProvider adds a provider adapter to the client.
func (c *Client) RegisterProvider(name string, adapter ProviderAdapter) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.providers[name] = adapter
	if c.defaultProvider == "" {
		c.defaultProvider = name
	}
}

// resolveProvider determines which provider adapter to use for a request.
func (c *Client) resolveProvider(req Request) (ProviderAdapter, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	name := req.Provider
	if name == "" {
		name = c.defaultProvider
	}
	if name == "" {
		// Try to infer from model catalog.
		if info := GetModelInfo(req.Model); info != nil {
			name = info.Provider
		}
	}
	if name == "" {
		return nil, &ConfigurationError{SDKError: SDKError{
			Message: "no provider specified and no default provider configured",
		}}
	}

	adapter, ok := c.providers[name]
	if !ok {
		return nil, &ConfigurationError{SDKError: SDKError{
			Message: fmt.Sprintf("provider %q is not registered", name),
		}}
	}
	return adapter, nil
}

// Complete sends a blocking request through middleware to the resolved provider.
func (c *Client) Complete(ctx context.Context, req Request) (*Response, error) {
	adapter, err := c.resolveProvider(req)
	if err != nil {
		return nil, err
	}

	// Ensure provider is set on request.
	if req.Provider == "" {
		req.Provider = adapter.Name()
	}

	// Build the middleware chain.
	handler := func(ctx context.Context, r Request) (*Response, error) {
		return adapter.Complete(ctx, r)
	}

	// Apply middleware in reverse order so first registered runs first.
	for i := len(c.middleware) - 1; i >= 0; i-- {
		mw := c.middleware[i]
		next := handler
		handler = func(ctx context.Context, r Request) (*Response, error) {
			return mw(ctx, r, next)
		}
	}

	return handler(ctx, req)
}

// Stream sends a streaming request through middleware to the resolved provider.
func (c *Client) Stream(ctx context.Context, req Request) (<-chan StreamEvent, error) {
	adapter, err := c.resolveProvider(req)
	if err != nil {
		return nil, err
	}

	if req.Provider == "" {
		req.Provider = adapter.Name()
	}

	handler := func(ctx context.Context, r Request) (<-chan StreamEvent, error) {
		return adapter.Stream(ctx, r)
	}

	for i := len(c.streamMW) - 1; i >= 0; i-- {
		mw := c.streamMW[i]
		next := handler
		handler = func(ctx context.Context, r Request) (<-chan StreamEvent, error) {
			return mw(ctx, r, next)
		}
	}

	return handler(ctx, req)
}

// Close releases resources held by all registered providers.
func (c *Client) Close() error {
	c.mu.RLock()
	defer c.mu.RUnlock()
	var firstErr error
	for _, adapter := range c.providers {
		if closer, ok := adapter.(Closer); ok {
			if err := closer.Close(); err != nil && firstErr == nil {
				firstErr = err
			}
		}
	}
	return firstErr
}

// Module-level default client.

var (
	defaultClient     *Client
	defaultClientOnce sync.Once
	defaultClientMu   sync.RWMutex
)

// SetDefaultClient sets the module-level default client.
func SetDefaultClient(c *Client) {
	defaultClientMu.Lock()
	defer defaultClientMu.Unlock()
	defaultClient = c
}

// GetDefaultClient returns the module-level default client, lazily initializing
// it from environment variables if not already set.
func GetDefaultClient() *Client {
	defaultClientMu.RLock()
	if defaultClient != nil {
		c := defaultClient
		defaultClientMu.RUnlock()
		return c
	}
	defaultClientMu.RUnlock()

	defaultClientMu.Lock()
	defer defaultClientMu.Unlock()
	if defaultClient != nil {
		return defaultClient
	}

	// Lazy initialization from environment.
	defaultClient = NewClientFromEnv()
	return defaultClient
}

// NewClientFromEnv creates a Client by scanning environment variables for API keys
// and creating GollmAdapters for each detected provider.
func NewClientFromEnv() *Client {
	c := NewClient()

	// Register providers based on available environment variables.
	// The GollmAdapter handles provider-specific env var lookup internally.
	for _, provider := range []string{"openai", "anthropic"} {
		adapter, err := NewGollmAdapter(provider, "")
		if err == nil {
			c.RegisterProvider(provider, adapter)
		}
	}

	return c
}
