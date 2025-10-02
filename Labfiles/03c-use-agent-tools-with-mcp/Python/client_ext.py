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


# Force approval workflow to invoke our handler so we can approve calls.
mcp_tool.set_approval_mode("always")

# Bind tools at the AGENT level (difference from client.py which supplies toolset at run time)
toolset = ToolSet()
toolset.add(mcp_tool)


# Custom handler that auto-approves MCP tool calls
class CustomRunHandler(RunHandler):
    def submit_mcp_tool_approval(self, *, run, tool_call, **kwargs):  # noqa: D401 - SDK override
        # Auto-approve every MCP tool call. Add policy checks/logging here if desired.
        print(f"[Auto-Approve] MCP tool call: id={tool_call.id} name={getattr(tool_call, 'name', '')}")
        try:
            return ToolApproval(tool_call_id=tool_call.id, approve=True)
        except TypeError:
            # Fallback in case constructor signature differs (older preview versions)
            return ToolApproval(tool_call.id, True)


# Use our custom handler that auto-approves MCP tool calls
run_handler = CustomRunHandler()

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

    # # Create thread for communication
    # thread = agents_client.threads.create()
    # print(f"Created thread, ID: {thread.id}")
    #
    # # Create a message on the thread
    # prompt = input("\nHow can I help?: ")
    # message = agents_client.messages.create(
    #     thread_id=thread.id,
    #     role="user",
    #     content=prompt,
    # )
    # print(f"Created message, ID: {message.id}")
    #
    # # Create and process agent run in thread using the run_handler (required when tools bound at agent level)
    # run = agents_client.runs.create_and_process(thread_id=thread.id, agent_id=agent.id, run_handler=run_handler)
    # # Check run status
    # print(f"Run completed with status: {run.status}")
    # if run.status == "failed":
    #     print(f"Run failed: {run.last_error}")
    #
    # # Display run steps and tool calls
    # run_steps = agents_client.run_steps.list(thread_id=thread.id, run_id=run.id)
    # for step in run_steps:
    #     print(f"Step {step['id']} status: {step['status']}")
    #
    #     # Check if there are tool calls in the step details
    #     step_details = step.get("step_details", {})
    #     tool_calls = step_details.get("tool_calls", [])
    #
    #     if tool_calls:
    #         # Display the MCP tool call details
    #         print("  MCP Tool calls:")
    #         for call in tool_calls:
    #             print(f"    Tool Call ID: {call.get('id')}")
    #             print(f"    Type: {call.get('type')}")
    #             print(f"    Name: {call.get('name')}")
    #
    #     print()  # add an extra newline between steps
    #
    # # Fetch and log all messages
    # messages = agents_client.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
    # print("\nConversation:")
    # print("-" * 50)
    # for msg in messages:
    #     if msg.text_messages:
    #         last_text = msg.text_messages[-1]
    #         print(f"{msg.role.upper()}: {last_text.text.value}")
    #         print("-" * 50)
    #
    # # Clean-up and delete the agent once the run is finished.
    # agents_client.delete_agent(agent.id)
    # print("Deleted agent")