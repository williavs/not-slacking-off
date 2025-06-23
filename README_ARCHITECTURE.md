# MCP AI Bot - Technical Architecture

## 1. System Overview

```
┌─────────────┐  user message   ┌──────────────┐  enriched prompt ┌──────────────┐
│  Slack App  ├───────────────▶│  Router LLM  ├──────────────────▶│   Finder     │
│ (`slack-    │                │  (gpt-4.1-   │                  │   Agent      │
│  bolt.py`)  │  response ◀────┤   mini)      │  answer  ◀───────┤(Confluence + │
└─────────────┘                └──────────────┘                  │  OpenAI)     │
                                                                  └──────────────┘
```

The MCP AI Bot is a multi-component system designed to provide intelligent responses to employee questions by leveraging internal knowledge bases. The architecture follows a modular design with these key components:

1. **Slack Front-End** – Receives `/ai …` questions, acknowledges receipt, and forwards them to the processing pipeline.
2. **Router LLM** – A lightweight `gpt-4.1-mini` model that classifies incoming questions into predefined categories.
3. **Context Builder** – Dynamically assembles the appropriate prompt and knowledge base content based on the question category.
4. **Finder Agent** – A powerful `gpt-4.1` model running within the MCP (Model Context Protocol) framework with access to Confluence tools.
5. **LangSmith Tracing** – Comprehensive observability layer that tracks all LLM interactions for debugging and improvement.
6. **DataDog Logs** - Application logging and monitoring integration.

All components operate asynchronously and share a thread-aware conversation memory system, enabling contextual follow-up questions in Slack threads.

## 2. Core Components

### 2.1 File Structure

| File/Directory | Purpose |
|----------------|---------|
| `bot.py`       | Core orchestration module that manages routing, context building, conversation memory, and MCP agent interactions |
| `slack-bolt.py`| Slack integration entry point that initializes the MCP app once on startup and routes messages to the processing pipeline |
| `knowledge_bases/` | Static knowledge files injected based on question category (e.g., `domain_kb.txt`, `policy_kb.txt`) |
| `prompts/`     | System prompts for different categories (`mcp.txt`, `domain.txt`, `policy.txt`) |
| `scripts/`     | Utility scripts including `atlassian_test_report.py` for API connectivity testing |
| `README.md`    | Extension guide for adding new capabilities to the bot |

### 2.2 Processing Pipeline

1. User sends a message via Slack (`/ai question`)
2. `slack-bolt.py` receives the message and calls `generate_response` in `bot.py`
3. `get_query_category` classifies the question using the Router LLM
4. Context builder assembles the appropriate prompt and knowledge base content
5. Conversation history is retrieved and appended to the context
6. The Finder Agent processes the enriched prompt using Confluence tools as needed
7. Response is returned to Slack and added to conversation memory

## 3. Intelligent Routing System

### 3.1 Category Configuration

Categories are defined in the `CATEGORIES` dictionary in `bot.py`:

```python
CATEGORIES = {
    "general": {
        "prompt_file": "prompts/mcp.txt",
        "kb_file": None,
        "description": "For questions about company policies, processes, and general information...",
        "aliases": ["general", "default", "company", "policy", "process"],
        "context_prefix": "**Answering a general company question.**"
    },
    "domain": {
        "prompt_file": "prompts/domain.txt",
        "kb_file": "knowledge_bases/domain_kb.txt",
        "description": "For specific questions about domain-specific topics...",
        "aliases": ["domain", "specific", "technical"],
        "context_prefix": "**Answering a domain-specific question. Here is relevant context:**"
    },
    # Additional categories...
}
```

### 3.2 Router Implementation

The router uses `gpt-4.1-mini` for efficient, cost-effective classification:

```python
async def get_query_category(user_message: str) -> str:
    response = await async_openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": ROUTER_PROMPT},
            {"role": "user", "content": user_message}
        ],
        temperature=0,
    )
    category = response.choices[0].message.content.strip().lower()
    
    # Validation logic and fallback to "general"
    # ...
    
    return category
```

The router prompt is dynamically generated from the category descriptions:

```python
ROUTER_PROMPT = """
You are a query router. Classify the user's question into one of the following categories and respond with ONLY the category name:
"""
# Dynamic generation from category descriptions
for category, config in CATEGORIES.items():
    ROUTER_PROMPT += f"\n- '{category}': {config['description']}"
```

## 4. MCP Agent Integration

### 4.1 Configuration

The MCP Agent is configured to connect to Atlassian services:

```python
# Construct Atlassian server arguments
atlassian_args = [
    "mcp-atlassian",
    f"--confluence-url={atlassian_confluence_url}",
    f"--confluence-username={atlassian_confluence_user}",
    # Additional configuration...
]

# Command-based configuration
settings = Settings(
    execution_engine="asyncio",
    logger=LoggerSettings(type="file", level="debug"),
    mcp=MCPSettings(servers={"atlassian": MCPServerSettings(command="uvx", args=atlassian_args)}),
    openai=OpenAISettings(api_key=os.environ.get("OPENAI_API_KEY"), default_model="gpt-4.1"),
)

mcp_app = MCPApp(name="mcp_unified_agent", settings=settings)
```

### 4.2 Agent Execution

The Finder Agent is created for each request and runs with the MCP framework:

```python
finder_agent = Agent(name="finder", instruction=PROMPTS["general"], server_names=["atlassian"])
async with finder_agent:
    llm = await finder_agent.attach_llm(OpenAIAugmentedLLM)
    result = await llm.generate_str(message=final_message)
```

### 4.3 Tool Usage Limits

The MCP Agent has configurable limits on tool usage:

- **Maximum iterations**: 10 per inference by default
- **Parallel tool calls**: Disabled by default
- Each iteration can involve LLM generation and tool usage

## 5. Conversation Memory System

### 5.1 Implementation

```python
class ConversationMemory:
    def __init__(self, max_messages: int = 50, ttl_hours: int = 24):
        self.conversations: Dict[str, List[ConversationMessage]] = {}
        self.max_messages = max_messages
        self.ttl_hours = ttl_hours
        
    # Methods for adding, retrieving messages, and cleanup...
```

### 5.2 Usage

- Thread-aware: Messages are stored by thread ID
- Auto-cleanup: 24-hour TTL with garbage collection
- Limited context: Only the last 10 messages are included in each prompt
- Format: `User: message\nAssistant: response`

## 6. LangSmith Tracing Integration

### 6.1 Configuration

LangSmith tracing is configured at startup:

```python
# Enable LangSmith tracing if API key is provided
if os.getenv("LANGCHAIN_TRACING_V2") == "true" and os.getenv("LANGCHAIN_API_KEY"):
    print("LangSmith tracing is enabled.")
    # Save original classes to avoid recursive wrapping
    _OriginalAsyncClient = openai.AsyncOpenAI
    _OriginalSyncClient = openai.OpenAI

    # Wrap both sync and async clients so all downstream usage is traced
    openai.AsyncOpenAI = lambda *args, **kwargs: wrap_openai(_OriginalAsyncClient(*args, **kwargs))
    openai.OpenAI = lambda *args, **kwargs: wrap_openai(_OriginalSyncClient(*args, **kwargs))
```

### 6.2 Traced Functions

The `@traceable` decorator is applied to key functions:

```python
@traceable(name="generate_response")
async def generate_response(message: str, thread_id: str) -> str:
    # Function implementation...
```

### 6.3 Environment Variables

Required environment variables for LangSmith:
- `LANGCHAIN_TRACING_V2="true"`
- `LANGCHAIN_API_KEY=<your-api-key>`
- `LANGCHAIN_ENDPOINT="https://api.smith.langchain.com"`
- `LANGSMITH_PROJECT=<project-name>`

## 7. Deployment Configuration

### 7.1 Helm Chart

The application is deployed using Helm with values defined in `helm/mcp_bot/values.yaml`:

```yaml
env:
  - name: OPENAI_API_KEY
    value: "WILL_BE_SET_BY_CI"
  - name: MCP_AGENT_CONFLUENCE_URL
    value: "https://company.atlassian.net/wiki"
  # Additional environment variables...
  - name: LANGCHAIN_TRACING_V2
    value: "true"
  - name: LANGCHAIN_API_KEY
    value: "WILL_BE_SET_BY_CI"
  - name: LANGCHAIN_ENDPOINT
    value: "https://api.smith.langchain.com"
  - name: LANGSMITH_PROJECT
    value: "WILL_BE_SET_BY_CI"
```

### 7.2 CircleCI Integration

The deployment pipeline is defined in `.circleci/config.yml`, which handles building the Docker image and deploying the Helm chart with the appropriate environment variables.

## 8. Extending the Bot

For detailed instructions on extending the bot with new capabilities, refer to the [Extension Guide](./README.md) which covers:

1. Adding new prompt files
2. Creating knowledge base files
3. Registering new categories in the router

## 9. Local Development

### 9.1 Setup

```bash
# Clone the repository
git clone <your-repository-url>
cd mcp-bot

# Install dependencies
pip install -r requirements.txt

# Create .env file with required environment variables
touch .env
# Add the necessary environment variables

# Run the bot
python slack-bolt.py
```

### 9.2 Testing Atlassian Connectivity

```bash
python scripts/atlassian_test_report.py
```

## 10. Troubleshooting

### Logs to Check

- Application logs for error messages
- LangSmith traces for detailed LLM interactions
- Slack API logs for message delivery issues

---
Open source MCP AI Bot for organizational knowledge management. 