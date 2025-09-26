import os

base_path = os.path.dirname(os.path.realpath(__file__))


def get_prompt(prompt_name: str) -> str:
    with open(base_path + "/" + prompt_name + ".md", "r", encoding="utf-8") as f:
        return f.read()
