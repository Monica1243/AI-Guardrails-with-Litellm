# guardrails-framework

A Python-based LLM guardrails framework integrated with the LiteLLM proxy. It intercepts requests before they reach an upstream model and runs them through a configurable validation pipeline — prebuilt validators first, then AI-powered validators.

---

## Architecture

```
Incoming LLM Request
        │
        ▼
┌───────────────────┐
│  LiteLLM Proxy    │ 
└────────┬──────────┘
         │
         ▼
┌───────────────────────────────────┐
│       GuardrailsFramework         │
│                                   │
│  Stage 1: Prebuilt Validators     │  
│  Stage 2: AI Validators           │ 
└───────────────────────────────────┘
         │
         ▼
   allowed / warned / redacted → request continues (possibly modified)
   blocked                     → request rejected immediately
```

---

## Validation Outcomes

| Outcome | Behavior |
|---------|----------|
| `allowed` | Input passes through unchanged |
| `warned` | Input passes through; warning recorded |
| `redacted` | Modified input passes through downstream stages |
| `blocked` | Pipeline stops; request is rejected |

---

## Configuration

All runtime behavior is controlled by `config.yml`.

```yaml
guardrails:
  failure_mode: closed        # "closed" = block on validator error, "open" = warn

  prebuilt_validators:
    - name: pii
      action: redact          # warn | redact | block
      timeout: 1000           # ms

  ai_validators:
    - name: prompt_injection
      action: block           # warn | redact | block
      timeout: 120000         # ms
```

---

## Running with Docker

The stack runs the LiteLLM proxy alongside an Ollama instance. Copy `.env.example` to `.env` and set your variables before starting.

```bash
docker compose up --build
```

The proxy will be available at `http://localhost:${LITELLM_PORT}`.