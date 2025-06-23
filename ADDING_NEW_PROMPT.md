# Adding a New Prompt Category to MCP-Bot

This guide walks through adding a new routing category to the MCP-Bot. As an example, we'll add a "support" category for questions about technical support, troubleshooting, and customer service processes.

## 1. Create the Knowledge Base Files

First, create the prompt and knowledge base files:

```bash
# Create the prompt file
touch mcp-bot/prompts/support.txt

# Create the knowledge base file
touch mcp-bot/knowledge_bases/support_kb.txt
```

### Example Prompt Content (`prompts/support.txt`)

```
You are an expert on technical support and customer service processes.

When answering questions about support operations, focus on:
- Troubleshooting methodologies
- Escalation procedures
- Customer communication best practices
- Service level agreements (SLAs)
- Support ticket management
- Knowledge base maintenance

Always be specific about proper procedures and response times.
Emphasize clear communication and systematic problem-solving approaches.
```

### Example Knowledge Base Content (`knowledge_bases/support_kb.txt`)

```
# Technical Support Knowledge Base

## Support Tiers
- Tier 1: Initial customer contact, basic troubleshooting
- Tier 2: Advanced technical issues, complex configuration
- Tier 3: Engineering escalation, product bugs, system issues

## Response Time SLAs
- Critical: 1 hour response, 4 hour resolution
- High: 4 hour response, 24 hour resolution
- Medium: 24 hour response, 3 day resolution
- Low: 3 day response, 1 week resolution

## Common Support Workflows
- Ticket creation and assignment
- Initial diagnosis and troubleshooting
- Documentation and knowledge base updates
- Customer communication and follow-up
- Escalation procedures

## Best Practices
- Always acknowledge receipt within 15 minutes
- Document all troubleshooting steps
- Update customers every 24 hours on open issues
- Follow up after resolution to ensure satisfaction
- Maintain detailed internal notes for future reference
```

## 2. Add the Category to the Configuration Dictionary

Simply add a new entry to the `CATEGORIES` dictionary in `bot.py`:

```python
CATEGORIES = {
    # ... existing categories ...
    "support": {
        "prompt_file": "prompts/support.txt",
        "kb_file": "knowledge_bases/support_kb.txt",
        "description": "For questions about technical support, customer service, troubleshooting procedures, or support operations.",
        "aliases": ["support", "help", "troubleshoot", "ticket", "customer service"],
        "context_prefix": "**Answering a question about support operations. Here is relevant context:**"
    }
}
```

That's it! The rest of the system automatically handles:
- Loading the prompt and knowledge base files
- Updating the router prompt with the new category
- Adding the category to the validation logic
- Building the context block when the category is selected

## 3. Test the New Category

Update `test_concurrent.py` to include support queries:

```python
SUPPORT_QUERIES = [
    "How do we handle escalated support tickets?",
    "What are our response time SLAs?",
    "How should we communicate with frustrated customers?",
    "What's the process for updating our knowledge base?",
]

# Then add to the scenarios dictionary:
scenarios = {
    "General": GENERAL_QUERIES,
    "Policy": POLICY_QUERIES,
    "Domain": DOMAIN_QUERIES,
    "Support": SUPPORT_QUERIES,
}
```

## 4. Run Tests

```bash
# First, run the test script to verify the new category works
python test_concurrent.py

# Then start the bot to test in Slack
python slack-bolt.py
```

## 5. Verify Routing

In Slack, test the routing with queries like:

- `/ai How do we handle critical support tickets?`
- `/ai What's our escalation process?`
- `/ai How should we respond to customer complaints?`

The router should classify these as "support" and include the specialized context.

## 6. Update Documentation

Update `README_ARCHITECTURE.md` to reflect the new category:

- Add "support" to the router description
- Update any diagrams or examples
- Add the new files to the file structure

## Understanding the Category Configuration

Each category in the `CATEGORIES` dictionary has the following properties:

| Property | Description | Example |
|----------|-------------|---------|
| `prompt_file` | Path to the prompt file (relative to BOT_DIR) | `"prompts/support.txt"` |
| `kb_file` | Path to the knowledge base file, or `None` if not needed | `"knowledge_bases/support_kb.txt"` |
| `description` | Description used in the router prompt | `"For questions about technical support..."` |
| `aliases` | List of keywords that help identify this category | `["support", "help", "troubleshoot"]` |
| `context_prefix` | Text that appears before the prompt in the context block | `"**Answering a question about support operations...**"` |

## Troubleshooting

If the router isn't correctly identifying your new category:

1. **Check the Aliases**: Add more relevant keywords to the `aliases` list.
2. **Improve the Description**: Make the category description more specific in the `description` field.
3. **Debug Router Output**: Add a temporary print statement in `get_query_category` to see the raw LLM output.
4. **Check File Paths**: Ensure the `prompt_file` and `kb_file` paths are correct.

## Best Practices

1. **Keep Knowledge Bases Focused**: Include only the most relevant information.
2. **Choose Distinct Aliases**: Avoid aliases that might overlap with other categories.
3. **Test Edge Cases**: Try queries that might be ambiguous between categories.
4. **Iterative Refinement**: Start simple and refine based on actual usage patterns.

---

By following these steps, you can easily add new specialized knowledge domains to the MCP-Bot without changing its core architecture. 