import os
from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent
from dotenv import load_dotenv, dotenv_values

from prompts.get_prompt import get_prompt
from tools.tools import all_tools

load_dotenv()


# TODO: read params from command line
def main():
    print("Hello from x2a-convertor!")
    print(get_prompt("system"))
    
    model = init_chat_model(os.getenv("LLM_MODEL"))

    agent = create_react_agent(
        model=model,
        tools=all_tools,
        prompt=get_prompt("system"),
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "what is the weather in san francisco?"}]}
    )
    print(result)


if __name__ == "__main__":
    main()
