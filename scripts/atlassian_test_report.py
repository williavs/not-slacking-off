import asyncio
import os
import time
from datetime import datetime
from typing import List, Dict, Any
import json
from dotenv import load_dotenv

from mcp_agent.app import MCPApp
from mcp_agent.config import Settings, LoggerSettings, MCPSettings, MCPServerSettings
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

# -----------------------------------------------------------------------------
# Configuration ----------------------------------------------------------------
# -----------------------------------------------------------------------------

DEFAULT_QUERIES: List[str] = [
    "ERTC deadline",
    "Employee onboarding process",
    "Gusto competitive analysis",
    "How to file IRS Form 941",
]

TIMEOUT_SECONDS = 15  # per query

# --- Load Environment Variables ---
load_dotenv()

# -----------------------------------------------------------------------------
# Helpers ----------------------------------------------------------------------
# -----------------------------------------------------------------------------

def build_app() -> MCPApp:
    """Create an MCPApp instance for testing."""
    inspector_url = os.environ.get("MCP_INSPECTOR_URL")
    
    if inspector_url:
        # Use URL-based configuration when Inspector URL is provided
        mcp_settings = MCPSettings(servers={
            "atlassian": MCPServerSettings(url=inspector_url)
        })
    else:
        # Use command-based configuration for local testing
        atlassian_confluence_url = os.environ.get("MCP_AGENT_CONFLUENCE_URL")
        atlassian_confluence_user = os.environ.get("MCP_AGENT_CONFLUENCE_USER")
        atlassian_confluence_token = os.environ.get("MCP_AGENT_CONFLUENCE_TOKEN")
        atlassian_jira_url = os.environ.get("MCP_AGENT_JIRA_URL")
        atlassian_jira_user = os.environ.get("MCP_AGENT_JIRA_USER")
        atlassian_jira_token = os.environ.get("MCP_AGENT_JIRA_TOKEN")
        atlassian_enabled_tools = os.environ.get("MCP_AGENT_ENABLED_TOOLS", "confluence_search,confluence_get_page")

        atlassian_args = [
            "mcp-atlassian",
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

        mcp_settings = MCPSettings(servers={
            "atlassian": MCPServerSettings(command="uvx", args=atlassian_args)
        })

    settings = Settings(
        execution_engine="asyncio",
        logger=LoggerSettings(type="console", level="info"),
        mcp=mcp_settings,
        openai=None,  # Not needed for this test script
    )
    return MCPApp(name="atlassian_test", settings=settings)


async def test_queries(queries: List[str]) -> List[Dict[str, Any]]:
    """Run each query through the confluence_search tool and collect metrics."""
    results: List[Dict[str, Any]] = []
    app = build_app()
    async with app.run():
        agent = Agent(
            name="atlassian_tester",
            instruction="You are testing the confluence_search tool. Return the number of hits and the first URL for each query.",
            server_names=["atlassian"],
        )
        async with agent:
            for q in queries:
                start_time = time.time()
                record: Dict[str, Any] = {"query": q, "top_hits": []}
                try:
                    tool_result = await agent.call_tool("confluence_search", {"query": q})
                    
                    if not tool_result.isError and tool_result.content and hasattr(tool_result.content[0], "text"):
                        json_string = tool_result.content[0].text
                        try:
                            hits = json.loads(json_string)
                            record["results"] = len(hits)
                            record["top_hits"] = [{"title": h.get("title", "N/A"), "url": h.get("url")} for h in hits[:3]]
                            record["status"] = "ok"
                        except (json.JSONDecodeError, IndexError) as e:
                            print(f"Error parsing tool result for query '{q}': {e}")
                            record["status"] = "parse error"
                            record["results"] = 0
                    else:
                        error_message = "unknown"
                        if tool_result.content and hasattr(tool_result.content[0], "text"):
                            error_message = tool_result.content[0].text
                        print(f"DEBUG: tool_result for query '{q}': {tool_result}")
                        record["status"] = f"tool error: {error_message}"
                        record["results"] = 0
                except asyncio.TimeoutError:
                    record["status"] = "timeout"
                    record["results"] = 0
                except Exception as e:
                    record["status"] = f"error: {e}"[:60]
                    record["results"] = 0
                
                end_time = time.time()
                record["elapsed"] = round(end_time - start_time, 2)
                results.append(record)
    return results


def print_report(rows: List[Dict[str, Any]]):
    """Pretty-print a simple table then a JSON dump for deeper inspection."""
    print("\nATLASSSIAN MCP TEST REPORT — " + datetime.utcnow().isoformat())
    print("=" * 80)
    
    for r in rows:
        print(f"Query: \"{r['query']}\" ({r.get('results', 0)} hits in {r.get('elapsed', 0.0):.2f}s) - Status: {r.get('status', 'error')}")
        if r.get('status') == 'ok' and r.get('top_hits'):
            for i, hit in enumerate(r.get('top_hits', [])):
                title = hit.get('title', 'No Title')
                url = hit.get('url', 'No URL')
                print(f"  {i+1}. {title}\n     L {url}")
        print("-" * 80)

    print("\nSUMMARY")
    total = len(rows)
    ok = sum(1 for r in rows if r['status'] == 'ok')
    timeouts = sum(1 for r in rows if r['status'] == 'timeout')
    errors = total - ok - timeouts
    print(f"  Total queries : {total}")
    print(f"  Successful    : {ok}")
    print(f"  Timeouts      : {timeouts}")
    print(f"  Errors        : {errors}\n")

    # dump raw json for offline inspection
    print("RAW JSON -> copy/paste into your editor if needed\n" + json.dumps(rows, indent=2))


async def main():
    queries = DEFAULT_QUERIES
    rows = await test_queries(queries)
    print_report(rows)


if __name__ == "__main__":
    asyncio.run(main()) 