"""Workshop settings. Save this file and the harness reloads with the new values."""

import os
from pathlib import Path

# Where things live. compose.yaml sets these; the defaults match it.
MODEL = os.getenv("MODEL", "qwen3.5:2b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "demo-kafka:19092")
LENSES_MCP_URL = os.getenv("LENSES_MCP_URL", "http://lenses-mcp:8000/mcp")
LENSES_ENVIRONMENT = os.getenv("LENSES_ENVIRONMENT", "demo")
FILES_DIR = Path(os.getenv("FILES_DIR", Path(__file__).resolve().parents[2] / "files"))

# Logging into Lenses (oauth.py). HQ has one address for your browser and another for the harness.
LENSES_HQ_URL = os.getenv("LENSES_HQ_URL", "http://lenses-hq:9991")
HARNESS_URL = os.getenv("HARNESS_URL", "http://localhost:8080")  # the harness as your browser sees it
OAUTH_STATE_FILE = Path(os.getenv("OAUTH_STATE_FILE", Path(__file__).resolve().parents[2] / ".lenses-oauth.json"))

SESSION_TOPIC = "agent.session"  # the log: only the harness writes here
PAYMENTS_TOPIC = "payments"  # the environment: the agent reads it, the verifier checks it

# 0 · Before any tools: /investigate must answer as JSON with an order_id, so the model makes one up
# (stage0.py). Set False to let it answer in plain text, where qwen3.5:2b says it can't see the cluster.
STAGE0_JSON = True

# 1 · Context manager
NUM_CTX = 8192  # Ollama's context length. Keep it constant, or Ollama reloads the model
NUM_PREDICT = 512  # the most tokens the model may generate in one call
WINDOW_BUDGET = 4000  # tokens one window may use, tool schemas included
KEEP_VERBATIM_STEPS = 2  # the newest steps keep their tool results whole

# 2 · Tool registry
REGISTER_ALL_MCP_TOOLS = False
MAX_TOOL_RESULT_CHARS = 2000

# 3 · Guardrails
MAX_STEPS = 6
RUN_TOKEN_BUDGET = 20_000

# 5 · Verifier
MAX_VERIFY_RETRIES = 1

# Sampling for Qwen3.5 without thinking. Ollama fills in its own defaults otherwise.
TEMPERATURE = 0.7
TOP_P = 0.8
TOP_K = 20

TASK_PROMPT = (
    "There is a payments topic on this Kafka cluster. Exactly one payment is invalid.\n"
    "Tell me its order_id and what is wrong with it."
)
