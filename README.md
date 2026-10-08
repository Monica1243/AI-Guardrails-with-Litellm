# AI Guardrails

A Python-based LLM guardrails integrated with the LiteLLM proxy.

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

## Running with Docker

The stack runs the LiteLLM proxy alongside an Ollama instance. Copy `.env.example` to `.env` and set your variables before starting.

```bash
docker compose up --build
```

The proxy will be available at `http://localhost:${LITELLM_PORT}`.
