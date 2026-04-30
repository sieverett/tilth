"""The agentic reasoning loop."""

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from tilth_agent.memory import load_memory
from tilth_agent.tools import TOOL_DEFINITIONS, ToolExecutor

log = logging.getLogger("tilth.agent")


def build_user_prompt(okrs_path: Path, memory_path: Path) -> str:
    """Construct the initial user prompt from OKRs and prior memory."""
    with open(okrs_path) as f:
        okrs = yaml.safe_load(f)

    prompt = "## Current Organizational Goals\n\n"
    for goal in okrs.get("goals", []):
        prompt += f"- **{goal['name']}**: {goal['target']}"
        if goal.get("current"):
            prompt += f" (current: {goal['current']})"
        if goal.get("period"):
            prompt += f" [{goal['period']}]"
        prompt += "\n"

    memory = load_memory(memory_path)
    if memory:
        prompt += f"\n## Your Memory From Prior Runs\n\n{memory}\n"
    else:
        prompt += "\n## Prior Memory\n\nThis is your first run. No prior memory.\n"

    prompt += (
        "\n## Your Task\n\n"
        "Analyze the organization's data against these goals. "
        "Start by understanding what data is available (describe_schema, "
        "list_records), then form hypotheses and search for evidence. "
        "Write actionable briefs for each finding. Save your updated "
        "memory when done."
    )
    return prompt


async def run_reasoning_loop(
    llm_client: Any,
    tool_executor: ToolExecutor,
    system_prompt: str,
    user_prompt: str,
    max_turns: int = 50,
) -> dict[str, Any]:
    """Run the agentic reasoning loop.

    Returns a summary dict with turn count, tool calls, and findings.
    """
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_prompt},
    ]

    stats = {
        "turns": 0,
        "tool_calls": 0,
        "findings_written": 0,
        "tokens_in": 0,
        "tokens_out": 0,
    }

    for turn in range(max_turns):
        stats["turns"] = turn + 1

        log.info("--- Turn %d ---", turn + 1)

        response = await llm_client.complete(
            messages=messages,
            system=system_prompt,
            tools=TOOL_DEFINITIONS,
            max_tokens=8192,
        )

        stats["tokens_in"] += response.usage.get("input_tokens", 0)
        stats["tokens_out"] += response.usage.get("output_tokens", 0)

        # Log any text output
        if response.text:
            log.info("Agent: %s", response.text[:500])

        # If no tool calls, the agent is done
        if response.stop_reason == "end_turn":
            log.info("Agent finished after %d turns", turn + 1)
            messages.append({"role": "assistant", "content": response.content})
            break

        # Process tool calls
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            tool_results: list[dict[str, Any]] = []
            for tool_call in response.tool_calls:
                stats["tool_calls"] += 1
                tool_name = tool_call["name"]
                tool_input = tool_call.get("input", {})
                tool_id = tool_call.get("id", "")

                log.info(
                    "Tool call: %s(%s)",
                    tool_name,
                    json.dumps(tool_input)[:200],
                )

                result = tool_executor.execute(tool_name, tool_input)

                if tool_name == "write_to_tilth":
                    stats["findings_written"] += 1

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result,
                })

            messages.append({"role": "user", "content": tool_results})

    log.info(
        "Run complete: %d turns, %d tool calls, %d findings, "
        "%d tokens in, %d tokens out",
        stats["turns"],
        stats["tool_calls"],
        stats["findings_written"],
        stats["tokens_in"],
        stats["tokens_out"],
    )

    return stats
