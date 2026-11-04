"""Explicit synthetic pilot: python -m src.core.groq_pilot --case volume."""
import argparse
import json
from src.config import settings
from src.integrations.groq_client import CASES, GroqPilotClient


def main():
    parser = argparse.ArgumentParser(description="Piloto Groq sintetico, sem executar ferramentas")
    parser.add_argument("--case", choices=tuple(CASES), required=True)
    args = parser.parse_args()
    client = GroqPilotClient(settings.groq_api_key,
                            enabled=settings.multi_llm_enabled,
                            free_plan_verified=settings.groq_free_plan_verified)
    result = client.run_case(args.case)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
