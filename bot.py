import asyncio
import os
from typing import Dict, List
from dataclasses import dataclass
from datetime import datetime, timedelta
from dotenv import load_dotenv
import openai

# --- LangSmith Tracing Setup ---
# This MUST be done before importing any modules that use the OpenAI client (e.g., mcp-agent)
from langsmith.wrappers import wrap_openai
from langsmith import traceable

load_dotenv()

# Enable LangSmith tracing if API key is provided.
# This "monkey-patches" the OpenAI client to add tracing to all calls.
if os.getenv("LANGCHAIN_TRACING_V2") == "true" and os.getenv("LANGCHAIN_API_KEY"):
    print("LangSmith tracing is enabled.")
    # Save original classes to avoid recursive wrapping
    _OriginalAsyncClient = openai.AsyncOpenAI
    _OriginalSyncClient = openai.OpenAI

    # Wrap both sync and async clients so all downstream usage is traced
    openai.AsyncOpenAI = lambda *args, **kwargs: wrap_openai(_OriginalAsyncClient(*args, **kwargs))
    openai.OpenAI = lambda *args, **kwargs: wrap_openai(_OriginalSyncClient(*args, **kwargs))
else:
    print("LangSmith tracing is disabled.")

# Now, import MCP modules that may use the (now patched) OpenAI client
from mcp_agent.app import MCPApp
from mcp_agent.config import (
    Settings,
    LoggerSettings,
    MCPSettings,
    MCPServerSettings,
    OpenAISettings,
)
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

# --- Initialize ASYNC OpenAI Client (now wrapped) ---
async_openai_client = openai.AsyncOpenAI()

# --- Load and Combine Prompts & Knowledge Bases at Startup ---
BOT_DIR = os.path.dirname(os.path.abspath(__file__))

def load_file(path: str) -> str:
    """Safely load a file's content."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Warning: File not found at {path}")
        return ""

# --- Category Configuration ---
# Central configuration point for all categories
# To add a new category, simply add a new entry to this dictionary

CATEGORIES = {
    "general": {
        "prompt_file": "prompts/mcp.txt",
        "kb_file": None,  # General doesn't have a separate KB file
        "description": "For questions about company policies, internal processes, or anything requiring a search of the internal knowledge base (Confluence). This is the default category for anything not clearly in another category.",
        "aliases": ["general", "default", "company", "policy", "process"],
        "context_prefix": "**Answering a general company question.**"
    },
    "ertc": {
        "prompt_file": "prompts/ertc.txt",
        "kb_file": "knowledge_bases/ertc_kb.txt",
        "description": "For specific questions about the Employee Retention Tax Credit, IRS rules, tax forms, deadlines, and financial reconciliation.",
        "aliases": ["ertc", "tax", "credit", "employee retention", "retention credit"],
        "context_prefix": "**Answering a question about ERTC. Here is relevant context:**"
    },
    "competitors": {
        "prompt_file": "prompts/competitors.txt",
        "kb_file": "knowledge_bases/competitors_kb.txt",
        "description": "For questions comparing this organization to other companies, or asking for 'battle cards' and competitive analysis.",
        "aliases": ["competitor", "competitors", "versus", "vs", "comparison", "other company", "alternative"],
        "context_prefix": "**Answering a question about competitors. Here is relevant context:**"
    }
    # To add a new category, simply add a new entry here following the same structure
    # Example:
    # "international": {
    #     "prompt_file": "prompts/international.txt",
    #     "kb_file": "knowledge_bases/international_kb.txt",
    #     "description": "For questions about international operations, global payroll, contractors in other countries, international compliance, or global HR capabilities.",
    #     "aliases": ["international", "global", "overseas", "foreign", "abroad"],
    #     "context_prefix": "**Answering a question about international operations. Here is relevant context:**"
    # }
}

# Load all prompts and knowledge bases based on the configuration
PROMPTS = {}
KNOWLEDGE_BASES = {}

for category, config in CATEGORIES.items():
    prompt_path = os.path.join(BOT_DIR, config["prompt_file"])
    PROMPTS[category] = load_file(prompt_path)
    
    if config["kb_file"]:
        kb_path = os.path.join(BOT_DIR, config["kb_file"])
        KNOWLEDGE_BASES[category] = load_file(kb_path)
    else:
        KNOWLEDGE_BASES[category] = ""

# --- Build the router prompt dynamically from the categories ---
ROUTER_PROMPT = """
You are a query router. Classify the user's question into one of the following categories and respond with ONLY the category name:
"""

for category, config in CATEGORIES.items():
    ROUTER_PROMPT += f"\n- '{category}': {config['description']}"

# --- Categorization using a smaller, faster model ---
async def get_query_category(user_message: str) -> str:
    """Uses gpt-4.1-mini to classify the user's query."""
    try:
        response = await async_openai_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": ROUTER_PROMPT},
                {"role": "user", "content": user_message}
            ],
            temperature=0,
        )
        category = response.choices[0].message.content.strip().lower()
        
        # Check for exact category match
        if category in CATEGORIES:
            print(f"Query categorized as: {category}")
            return category
        
        # Check for aliases/keywords in the response
        for cat, config in CATEGORIES.items():
            for alias in config["aliases"]:
                if alias in category:
                    print(f"Query categorized as: {cat} (matched alias: {alias})")
                    return cat
        
        # Default to general if no match
        print("Query categorized as: general (default)")
        return "general"
    except Exception as e:
        print(f"Error in query categorization: {e}. Defaulting to 'general'.")
        return "general"

# --- Conversation Memory  ---
@dataclass
class ConversationMessage:
    role: str
    content: str
    timestamp: datetime

class ConversationMemory:
    def __init__(self, max_messages: int = 50, ttl_hours: int = 24):
        self.conversations: Dict[str, List[ConversationMessage]] = {}
        self.max_messages = max_messages
        self.ttl_hours = ttl_hours

    def add_message(self, thread_id: str, role: str, content: str):
        if thread_id not in self.conversations:
            self.conversations[thread_id] = []
        message = ConversationMessage(role=role, content=content, timestamp=datetime.now())
        self.conversations[thread_id].append(message)
        if len(self.conversations[thread_id]) > self.max_messages:
            self.conversations[thread_id] = [self.conversations[thread_id][0]] + self.conversations[thread_id][-(self.max_messages - 1):]

    def get_conversation_history(self, thread_id: str) -> List[Dict[str, str]]:
        self._cleanup_expired_conversations()
        return [{"role": msg.role, "content": msg.content} for msg in self.conversations.get(thread_id, [])]

    def _cleanup_expired_conversations(self):
        cutoff = datetime.now() - timedelta(hours=self.ttl_hours)
        expired = [tid for tid, msgs in self.conversations.items() if msgs and msgs[-1].timestamp < cutoff]
        for tid in expired:
            del self.conversations[tid]

conversation_memory = ConversationMemory()

# --- MCP Agent Setup ---
atlassian_confluence_url = os.environ.get("MCP_AGENT_CONFLUENCE_URL")
atlassian_confluence_user = os.environ.get("MCP_AGENT_CONFLUENCE_USER")
atlassian_confluence_token = os.environ.get("MCP_AGENT_CONFLUENCE_TOKEN")
atlassian_jira_url = os.environ.get("MCP_AGENT_JIRA_URL")
atlassian_jira_user = os.environ.get("MCP_AGENT_JIRA_USER")
atlassian_jira_token = os.environ.get("MCP_AGENT_JIRA_TOKEN")
atlassian_enabled_tools = os.environ.get("MCP_AGENT_ENABLED_TOOLS", "confluence_search,confluence_get_page")

# Construct Atlassian server arguments
atlassian_args = [
    f"--confluence-url={atlassian_confluence_url}",
    f"--confluence-username={atlassian_confluence_user}",
]
if atlassian_confluence_token:
    atlassian_args.append(f"--confluence-token={atlassian_confluence_token}")
atlassian_args.extend([
    f"--jira-url={atlassian_jira_url}",
    f"--jira-username={atlassian_jira_user}",
])
if atlassian_jira_token:
    atlassian_args.append(f"--jira-token={atlassian_jira_token}")
atlassian_args.append(f"--enabled-tools={atlassian_enabled_tools}")

# Use console-script 'mcp-atlassian' directly
command = "mcp-atlassian"

# Always use command-based configuration
settings = Settings(
    execution_engine="asyncio",
    logger=LoggerSettings(type="file", level="debug"),
    mcp=MCPSettings(servers={"atlassian": MCPServerSettings(command=command, args=atlassian_args)}),
    openai=OpenAISettings(api_key=os.environ.get("OPENAI_API_KEY"), default_model="gpt-4.1"),
)

mcp_app = MCPApp(name="mcp_unified_agent", settings=settings)

# --- Main Response Generation Logic ---
@traceable(name="generate_response")
async def generate_response(message: str, thread_id: str) -> str:
    """Orchestrates the agentic response generation."""
    try:
        # The MCPApp is now started by the main application entrypoint (slack-bolt.py)
        # This function assumes the app's services are already running.

        # 1. Categorize the user's query
        category = await get_query_category(message)

        # 2. Dynamically build a context block for the selected category
        context_block = ""
        if category != "general" and category in CATEGORIES:
            prompt = PROMPTS.get(category, "")
            kb = KNOWLEDGE_BASES.get(category, "")
            prefix = CATEGORIES[category]["context_prefix"]
            
            if prompt and kb:
                context_block = f"{prefix}\n{prompt}\n\n{kb}\n---"
            elif prompt:
                context_block = f"{prefix}\n{prompt}\n---"

        # 3. Handle conversation history
        history = conversation_memory.get_conversation_history(thread_id)
        history_str = "\n".join([f"{msg['role'].title()}: {msg['content']}" for msg in history[-10:]])

        # 4. Construct the final message for the agent
        final_message = f"{context_block}\n\nPrevious conversation:\n{history_str}\n\nCurrent question: {message}"

        # 5. Run the agent
        finder_agent = Agent(name="finder", instruction=PROMPTS["general"], server_names=["atlassian"])
        async with finder_agent:
            llm = await finder_agent.attach_llm(OpenAIAugmentedLLM)
            result = await llm.generate_str(message=final_message)

            # 6. Update conversation memory
            conversation_memory.add_message(thread_id, "user", message)
            conversation_memory.add_message(thread_id, "assistant", result)

            return result

    except Exception as e:
        print(f"Error during agentic response generation: {e}")
        return "Sorry, I encountered an error while processing your request with my internal tools."