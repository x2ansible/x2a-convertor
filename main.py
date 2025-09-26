import os
import logging
import sys

from langchain.chat_models import init_chat_model
from langchain.globals import set_debug
from langgraph.prebuilt import create_react_agent
from dotenv import load_dotenv

from prompts.get_prompt import get_prompt
from tools.tools import all_tools


def setup_logging():
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(stream=sys.stderr, level=log_level)
    if log_level == "DEBUG":
        set_debug(True)


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
        {
            "messages": [
                {"role": "user", "content": "what is the weather in san francisco?"}
            ]
        }
    )
    print(result)


load_dotenv()
setup_logging()

if __name__ == "__main__":
    main()
