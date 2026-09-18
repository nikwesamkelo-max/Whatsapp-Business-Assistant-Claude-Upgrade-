"""
setup_managed_agent.py — run ONCE to create your Managed Agent and its
environment. Save the printed IDs as environment variables - you'll pass
them to managed_assistant.py on every run (agents are long-lived
resources you reference by ID, not something you recreate per message).

Managed Agents is a beta feature. It may not be enabled on every account
yet, and the exact field names below are based on the current beta docs
- if a call fails with an unexpected shape, check
https://platform.claude.com/docs/en/managed-agents/overview for the
latest schema before assuming your code is wrong.

Usage:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python3 setup_managed_agent.py
    # then save the two printed IDs, e.g.:
    export MANAGED_AGENT_ID="agent_..."
    export MANAGED_ENVIRONMENT_ID="env_..."
"""

from anthropic import Anthropic

client = Anthropic()

SYSTEM_PROMPT = """You are the WhatsApp Business Assistant for a small
event rental business. Greet customers warmly and keep replies short and
friendly, like a real WhatsApp message - one or two sentences, no markdown
formatting.

For ANY question about services, pricing, hours, policies, or FAQs, use the
search_knowledge_base tool first and answer only from what it returns.
Never guess or make up details.

Help customers book by collecting a preferred date and time, then
confirming with the start_booking tool.

When the customer shares something worth remembering for next time (a
preference, event type, accessibility need), save it with
update_customer_profile."""

# Same three tools as assistant.py, expressed as Managed Agents "custom"
# tools - our code executes them, the agent just decides when to call them.
CUSTOM_TOOLS = [
    {
        "type": "custom",
        "name": "search_knowledge_base",
        "description": (
            "Search the business's knowledge base (services, pricing, hours, "
            "policies, FAQs) for information relevant to the customer's question."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "type": "custom",
        "name": "start_booking",
        "description": "Create a booking once the customer has given both a preferred date and time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "preferred_date": {"type": "string"},
                "preferred_time": {"type": "string"},
            },
            "required": ["preferred_date", "preferred_time"],
        },
    },
    {
        "type": "custom",
        "name": "update_customer_profile",
        "description": "Save a durable fact about this customer for future conversations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["key", "value"],
        },
    },
]


def main():
    agent = client.beta.agents.create(
        name="whatsapp-business-assistant",
        model="claude-sonnet-4-6",
        system=SYSTEM_PROMPT,
        tools=CUSTOM_TOOLS,
    )
    print(f"Agent created: {agent.id} (version {agent.version})")

    # Limited networking - our tools run on OUR side (SQLite + rag.py),
    # the sandbox itself doesn't need internet access. Matches the
    # pattern Anthropic's own examples use for custom-tool-only agents.
    environment = client.beta.environments.create(
        name="whatsapp-assistant-env",
        config={
            "type": "cloud",
            "networking": {
                "type": "limited",
                "allowed_hosts": [],
                "allow_package_managers": False,
                "allow_mcp_servers": False,
            },
        },
    )
    print(f"Environment created: {environment.id}")

    print()
    print("Save these and export them before running managed_assistant.py:")
    print(f'  export MANAGED_AGENT_ID="{agent.id}"')
    print(f'  export MANAGED_ENVIRONMENT_ID="{environment.id}"')


if __name__ == "__main__":
    main()
