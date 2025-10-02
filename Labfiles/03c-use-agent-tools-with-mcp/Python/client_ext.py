import os
from dotenv import load_dotenv

# Add references
from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import McpTool, ToolSet, ListSortOrder, RunHandler, ToolApproval

# Load environment variables from .env file
load_dotenv()
project_endpoint = os.getenv("PROJECT_ENDPOINT")
model_deployment = os.getenv("MODEL_DEPLOYMENT_NAME")

if not project_endpoint or not model_deployment:
    raise ValueError("PROJECT_ENDPOINT and MODEL_DEPLOYMENT_NAME must be set in your environment (.env file).")

# Connect to the agents client (synchronous version). For async usage, switch to the aio client + AsyncRunHandler.
agents_client = AgentsClient(
    endpoint=project_endpoint,
    credential=DefaultAzureCredential(
        exclude_environment_credential=True,
        exclude_managed_identity_credential=True
    )
)

# MCP server configuration
mcp_server_url = "https://learn.microsoft.com/api/mcp"
mcp_server_label = "mslearn"

# Initialize agent MCP tool
mcp_tool = McpTool(
    server_label=mcp_server_label,
    server_url=mcp_server_url,
)


class AutoApprovalRunHandler(RunHandler):
    """A custom RunHandler that automatically approves all MCP tool calls."""
    def submit_mcp_tool_approval(self, *, run, tool_call, **kwargs):
        print(f"[Auto-Approve] MCP tool call: id={tool_call.id} name={getattr(tool_call, 'name', '')}")
        return ToolApproval(tool_call_id=tool_call.id, approve=True)


class InteractiveRunHandler(RunHandler):
    """A custom RunHandler that prompts the user to approve or reject MCP tool calls."""
    def submit_mcp_tool_approval(self, *, run, tool_call, **kwargs):
        # Prompt user to approve or reject the MCP tool call
        print(f"[User Approval Required] MCP tool call: id={tool_call.id} name={getattr(tool_call, 'name', '')}")
        while True:
            user_input = input("Approve this tool call? (y/n): ").strip().lower()
            if user_input in ('y', 'yes'):
                print("Tool call approved.")
                return ToolApproval(tool_call_id=tool_call.id, approve=True)
            elif user_input in ('n', 'no'):
                print("Tool call rejected.")
                return ToolApproval(tool_call_id=tool_call.id, approve=False)
            else:
                print("Invalid input. Please enter 'y' or 'n'.")

if (
    os.environ.get("REQUIRE_APPROVAL", "false").lower()
    in ("1", "true", "yes")
):
    print("MCP tool calls will require user approval.")
    run_handler = InteractiveRunHandler()
    mcp_tool.set_approval_mode("always")
else:
    print("MCP tool calls will be auto-approved.")
    run_handler = AutoApprovalRunHandler()
    mcp_tool.set_approval_mode("never")

# Bind tools at the AGENT level (difference from client.py which supplies toolset at run time)
toolset = ToolSet()
toolset.add(mcp_tool)


# Create agent with MCP tool and process agent run
with agents_client:

    # Create a new agent with MCP tools bound at creation
    agent = agents_client.create_agent(
        model=model_deployment,
        name="my-mcp-agent",
        instructions="""
        You have access to an MCP server called `microsoft.docs.mcp` - this tool allows you to 
        search through Microsoft's latest official documentation. Use the available MCP tools 
        to answer questions and perform tasks.""",
        toolset=toolset,
    )

    # Log info
    print(f"Created agent, ID: {agent.id}")
    print(f"MCP Server: {mcp_tool.server_label} at {mcp_tool.server_url}")

    # Create thread for communication
    thread = agents_client.threads.create()
    print(f"Created thread, ID: {thread.id}")

    # Create a message on the thread
    prompt = input("\nHow can I help?: ")
    message = agents_client.messages.create(
        thread_id=thread.id,
        role="user",
        content=prompt,
    )
    print(f"Created message, ID: {message.id}")

    # Create and process agent run in thread using the run_handler (required when tools bound at agent level)
    run = agents_client.runs.create_and_process(thread_id=thread.id, agent_id=agent.id, run_handler=run_handler)
    # Check run status
    print(f"Run completed with status: {run.status}")
    if run.status == "failed":
        print(f"Run failed: {run.last_error}")

    # Display run steps and tool calls
    run_steps = agents_client.run_steps.list(thread_id=thread.id, run_id=run.id)
    for step in run_steps:
        print(f"Step {step['id']} status: {step['status']}")

        # Check if there are tool calls in the step details
        step_details = step.get("step_details", {})
        tool_calls = step_details.get("tool_calls", [])

        if tool_calls:
            # Display the MCP tool call details
            print("  MCP Tool calls:")
            for call in tool_calls:
                print(f"    Tool Call ID: {call.get('id')}")
                print(f"    Type: {call.get('type')}")
                print(f"    Name: {call.get('name')}")

        print()  # add an extra newline between steps

    # Fetch and log all messages
    messages = agents_client.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
    print("\nConversation:")
    print("-" * 50)
    for msg in messages:
        if msg.text_messages:
            last_text = msg.text_messages[-1]
            print(f"{msg.role.upper()}: {last_text.text.value}")
            print("-" * 50)

    # Clean-up and delete the agent once the run is finished.
    agents_client.delete_agent(agent.id)
    print("Deleted agent")