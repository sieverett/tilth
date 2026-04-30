"""Entry point: python -m tilth_agent"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from tilth_agent.reasoning import build_user_prompt, run_reasoning_loop
from tilth_agent.tools import ToolExecutor


def main() -> None:
    # Configure logging
    log_level = os.environ.get("TILTH_AGENT_LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )

    # Paths
    base_dir = Path(__file__).parent.parent.parent
    prompts_dir = Path(__file__).parent / "prompts"
    config_dir = base_dir / "config"
    data_dir = base_dir / "data"

    system_prompt_path = prompts_dir / "system.md"
    okrs_path = config_dir / "okrs.yaml"
    memory_path = data_dir / "agent-memory.md"

    # Config from env
    gateway_url = os.environ.get(
        "TILTH_QUERY_GATEWAY_URL", "http://localhost:8002"
    )
    identity = os.environ.get("TILTH_IDENTITY", "ops-copilot")

    # Set TILTH_GATEWAY_URL for write_to_tilth (uses tilth client library)
    os.environ.setdefault("TILTH_GATEWAY_URL", "http://localhost:8001")
    os.environ.setdefault("TILTH_IDENTITY", identity)

    # Load system prompt
    system_prompt = system_prompt_path.read_text()

    # Build user prompt from OKRs + memory
    user_prompt = build_user_prompt(okrs_path, memory_path)

    # Create LLM client
    sys.path.insert(
        0,
        str(Path(__file__).parent.parent.parent.parent / "tilth-server" / "src"),
    )
    from tilth_server._shared.models import create_llm_client

    llm = create_llm_client()

    # Create tool executor
    executor = ToolExecutor(
        gateway_url=gateway_url,
        identity=identity,
        memory_path=memory_path,
    )

    print(f"Tilth Reasoning Agent")
    print(f"  LLM: {llm.model_name}")
    print(f"  Gateway: {gateway_url}")
    print(f"  Identity: {identity}")
    print(f"  Memory: {memory_path}")
    print()

    try:
        stats = asyncio.run(
            run_reasoning_loop(
                llm_client=llm,
                tool_executor=executor,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        )
        print(f"\n--- Run Summary ---")
        print(f"  Turns: {stats['turns']}")
        print(f"  Tool calls: {stats['tool_calls']}")
        print(f"  Findings written: {stats['findings_written']}")
        print(f"  Tokens: {stats['tokens_in']} in / {stats['tokens_out']} out")
    finally:
        executor.close()


if __name__ == "__main__":
    main()
