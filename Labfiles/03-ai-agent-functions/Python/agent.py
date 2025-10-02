import os
from dotenv import load_dotenv

# Add references
from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import FunctionTool, ToolSet, ListSortOrder, MessageRole
from user_functions import user_functions


def main():
    os.system("cls" if os.name == "nt" else "clear")  # Clear the console

    load_dotenv()  # Load environment variables
    project_endpoint = os.getenv("PROJECT_ENDPOINT")
    model_deployment = os.getenv("MODEL_DEPLOYMENT_NAME")

    agent_client = AgentsClient(
        endpoint=project_endpoint,
        credential=DefaultAzureCredential(
            exclude_environment_credential=True,
            exclude_managed_identity_credential=True,
        ),
    )

    with agent_client:  # Define an agent that can use the custom functions
        functions = FunctionTool(user_functions)
        toolset = ToolSet()
        toolset.add(functions)
        agent_client.enable_auto_function_calls(toolset)

        agent = agent_client.create_agent(
            model=model_deployment,
            name="support-agent",
            instructions="""You are a technical support agent.
When a user has a technical issue, you get their email address and a description of the issue.
Then you use those values to submit a support ticket using the function available to you.
If a file is saved, tell the user the file name.
""",
            toolset=toolset,
        )

        thread = agent_client.threads.create()
        print(f"You're chatting with: {agent.name} ({agent.id})")

        while True:  # Loop until user quits
            user_prompt = input("Enter a prompt (or type 'quit' to exit): ")
            if user_prompt.lower() == "quit":
                break
            if not user_prompt:
                print("Please enter a prompt.")
                continue

            agent_client.messages.create(
                thread_id=thread.id,
                role="user",
                content=user_prompt,
            )  # Send a prompt to the agent
            run = agent_client.runs.create_and_process(
                thread_id=thread.id, agent_id=agent.id
            )

            if run.status == "failed":  # Check the run status for failures
                print(f"Run failed: {run.last_error}")
                continue

            last_msg = agent_client.messages.get_last_message_text_by_role(  # Show the latest response
                thread_id=thread.id,
                role=MessageRole.AGENT,
            )
            if last_msg:
                print(f"Last Message: {last_msg.text.value}")

        print("\nConversation Log:\n")  # Get the conversation history
        messages = agent_client.messages.list(
            thread_id=thread.id, order=ListSortOrder.ASCENDING
        )
        for message in messages:
            if message.text_messages:
                last_text_msg = message.text_messages[-1]
                print(f"{message.role}: {last_text_msg.text.value}\n")

        agent_client.delete_agent(agent.id)  # Clean up
        print("Deleted agent")


if __name__ == "__main__":
    main()
