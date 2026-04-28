"""One-shot smoke test: confirm we can reach Claude on Bedrock with the
current AWS credentials and that model access is enabled.

Usage:
    CLAUDE_CODE_USE_BEDROCK=1 AWS_PROFILE=... AWS_REGION=us-east-1 \
        python -m scripts.probe_bedrock

Exits 0 on success, non-zero on failure with a human-readable hint.
"""
from __future__ import annotations

import asyncio
import os
import sys
import traceback

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    query,
)


async def main() -> int:
    use_bedrock = os.environ.get("CLAUDE_CODE_USE_BEDROCK", "").strip() in ("1", "true", "yes")
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    profile = os.environ.get("AWS_PROFILE")

    if not use_bedrock:
        print("CLAUDE_CODE_USE_BEDROCK is not set — set it to '1' to probe Bedrock.")
        return 2
    if not region:
        print("AWS_REGION is not set — pick a Bedrock-enabled region (e.g. us-east-1).")
        return 2

    print(f"Probing Bedrock: region={region}  profile={profile or '(default)'}")
    model = os.environ.get("HELPDESK_MODEL") or "us.anthropic.claude-sonnet-4-6"
    options = ClaudeAgentOptions(
        system_prompt="Reply in one short sentence.",
        model=model,
        max_turns=1,
    )
    try:
        async for msg in query(prompt="Say 'pong' and nothing else.", options=options):
            if isinstance(msg, ResultMessage):
                txt = (getattr(msg, "result", None) or "").strip()
                print(f"OK ✓ model={model} reply={txt!r}")
                return 0
        print("WARN — query stream ended without a ResultMessage.")
        return 3
    except Exception as e:  # noqa: BLE001
        print(f"FAIL — {type(e).__name__}: {e}")
        msg = str(e).lower()
        if "accessdenied" in msg or "not authorized" in msg or "validationexception" in msg:
            print("\nLikely cause: model access not enabled in this AWS account/region.")
            print("Fix: AWS console → Bedrock → Model access → request access for the")
            print("     'Anthropic Claude Sonnet 4.6' (or equivalent) inference profile.")
        elif "could not load credentials" in msg or "unable to locate credentials" in msg:
            print("\nLikely cause: AWS credentials not visible.")
            print("Fix: export AWS_PROFILE=<profile-with-bedrock-access>, or run")
            print("     `aws sso login --profile <profile>` first.")
        elif "endpoint" in msg or "could not connect" in msg:
            print("\nLikely cause: bad region or network.")
        else:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
