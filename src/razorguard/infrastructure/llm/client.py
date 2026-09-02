"""
LLM client — thin wrapper supporting Claude, OpenAI, and Gemini.

SECURITY:
- LLM output is ALWAYS treated as untrusted
- No credentials inside prompts
- No payment data in LLM context
- Tool results are DATA, never instructions
- Final authorization is always outside LLM context

The client is model-switchable via LLM_PROVIDER env var.
"""

from typing import Any

from razorguard.infrastructure.observability.logging import get_logger
from razorguard.shared.config import get_settings

logger = get_logger(__name__)


def _openai_tools(tools: list[dict] | None) -> list[dict]:
    """Translate RazorGuard's canonical tool schema for OpenAI-compatible SDKs."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }
        for tool in (tools or [])
    ]


def get_llm_client():
    """Return the configured LLM client (Claude, OpenAI, or Gemini)."""
    settings = get_settings()
    if settings.llm_provider == "claude":
        import anthropic

        return anthropic.Anthropic(api_key=settings.anthropic_api_key)
    if settings.llm_provider == "gemini":
        from google import genai

        return genai.Client(api_key=settings.gemini_api_key)
    import openai

    if settings.llm_provider == "groq":
        return openai.OpenAI(
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )
    return openai.OpenAI(api_key=settings.openai_api_key)


async def call_llm(
    *,
    system_prompt: str,
    user_message: str,
    tools: list[dict] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """
    Call the configured LLM with optional tool definitions.

    Returns a dict with:
      - content: text response (if no tool call)
      - tool_calls: list of tool call requests (if LLM wants to use tools)
      - model: which model responded
      - raw: the full provider response

    SECURITY: The caller must validate ALL tool call arguments
    before executing them. Never trust tool call arguments directly.
    """
    settings = get_settings()

    if settings.llm_provider == "claude":
        return await _call_claude(
            system_prompt=system_prompt,
            user_message=user_message,
            tools=tools,
            model=model or settings.llm_model_claude,
        )
    if settings.llm_provider == "gemini":
        return await _call_gemini(
            system_prompt=system_prompt,
            user_message=user_message,
            tools=tools,
            model=model or settings.llm_model_gemini,
        )
    if settings.llm_provider == "groq":
        return await _call_openai_compatible(
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
            system_prompt=system_prompt,
            user_message=user_message,
            tools=tools,
            model=model or settings.llm_model_groq,
        )
    return await _call_openai(
        system_prompt=system_prompt,
        user_message=user_message,
        tools=tools,
        model=model or settings.llm_model_openai,
    )


async def _call_claude(
    *,
    system_prompt: str,
    user_message: str,
    tools: list[dict] | None,
    model: str,
) -> dict[str, Any]:
    import anthropic

    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": settings.llm_max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}],
    }
    if tools:
        kwargs["tools"] = tools

    response = client.messages.create(**kwargs)

    tool_calls = []
    text_content = ""
    for block in response.content:
        if block.type == "tool_use":
            tool_calls.append(
                {
                    "tool_name": block.name,
                    "tool_input": block.input,
                    "tool_use_id": block.id,
                }
            )
        elif block.type == "text":
            text_content = block.text

    return {
        "content": text_content,
        "tool_calls": tool_calls,
        "model": model,
        "stop_reason": response.stop_reason,
    }


async def _call_openai(
    *,
    system_prompt: str,
    user_message: str,
    tools: list[dict] | None,
    model: str,
) -> dict[str, Any]:
    settings = get_settings()
    return await _call_openai_compatible(
        api_key=settings.openai_api_key,
        base_url=None,
        system_prompt=system_prompt,
        user_message=user_message,
        tools=tools,
        model=model,
    )


async def _call_openai_compatible(
    *,
    api_key: str,
    base_url: str | None,
    system_prompt: str,
    user_message: str,
    tools: list[dict] | None,
    model: str,
) -> dict[str, Any]:
    """Run an OpenAI Chat Completions-compatible provider, including Groq."""
    import openai

    settings = get_settings()
    client = openai.OpenAI(api_key=api_key, base_url=base_url)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": settings.llm_max_tokens,
        "temperature": settings.llm_temperature,
    }
    if tools:
        kwargs["tools"] = _openai_tools(tools)
        kwargs["tool_choice"] = "auto"

    response = client.chat.completions.create(**kwargs)
    message = response.choices[0].message

    tool_calls = []
    if message.tool_calls:
        import json

        for tc in message.tool_calls:
            tool_calls.append(
                {
                    "tool_name": tc.function.name,
                    "tool_input": json.loads(tc.function.arguments),
                    "tool_use_id": tc.id,
                }
            )

    return {
        "content": message.content or "",
        "tool_calls": tool_calls,
        "model": model,
        "stop_reason": response.choices[0].finish_reason,
    }


async def _call_gemini(
    *,
    system_prompt: str,
    user_message: str,
    tools: list[dict] | None,
    model: str,
) -> dict[str, Any]:
    """Call Gemini and normalize its function calls to RazorGuard's safe tool format."""
    from google import genai
    from google.genai import types

    settings = get_settings()
    client = genai.Client(api_key=settings.gemini_api_key)

    # Buyer-agent tools are maintained as OpenAI-compatible function schemas.
    # Gemini uses the same JSON schema payload under ``function_declarations``.
    declarations = [tool["function"] for tool in _openai_tools(tools)]
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=settings.llm_temperature,
        max_output_tokens=settings.llm_max_tokens,
        tools=[types.Tool(function_declarations=declarations)] if declarations else None,
    )
    response = await client.aio.models.generate_content(
        model=model,
        contents=user_message,
        config=config,
    )

    tool_calls = []
    for call in response.function_calls or []:
        tool_calls.append(
            {
                "tool_name": call.name,
                "tool_input": dict(call.args or {}),
                "tool_use_id": getattr(call, "id", None) or call.name,
            }
        )

    # ``GenerateContentResponse.text`` intentionally raises when the response
    # contains a function call rather than a text part. Read text parts
    # directly so a tool-only turn can continue to the controlled executor.
    text_parts: list[str] = []
    for candidate in response.candidates or []:
        for part in candidate.content.parts or []:
            if part.text:
                text_parts.append(part.text)

    return {
        "content": "\n".join(text_parts),
        "tool_calls": tool_calls,
        "model": model,
        "stop_reason": "tool_use" if tool_calls else "stop",
    }
