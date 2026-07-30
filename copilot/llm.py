"""
llm.py

Returns a real chat model when ANTHROPIC_API_KEY is set, else None. Every
caller in copilot/ is written to work either way: with a model, it builds
a LangChain agent that calls tools and writes the final answer itself;
without one, it falls back to the deterministic paths in
fallback_parser.py / sql_tool.py's canned questions.

This project was built and tested without a configured key, so the
real-model path is correct against the installed langchain-anthropic API
but has not been exercised end to end here -- see the README.
"""

from __future__ import annotations

import os

_MODEL_NAME = "claude-sonnet-4-6"


def get_llm():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(model=_MODEL_NAME, temperature=0)


def llm_available() -> bool:
    return get_llm() is not None
