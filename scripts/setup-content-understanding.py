#!/usr/bin/env python3
"""
Setup Content Understanding Analyzer

This script:
1. Configures model deployment defaults (maps model names to your deployment names)
2. Creates the custom 'customsDeclaration' analyzer from infrastructure/customs-analyzer.json

Usage:
    # Using Azure CLI auth (recommended for local dev):
    python scripts/setup-content-understanding.py

    # With environment variables (same as backend/.env):
    AZURE_CONTENT_UNDERSTANDING_ENDPOINT=https://your-resource.services.ai.azure.com/ \\
        python scripts/setup-content-understanding.py

    # Pass deployment names explicitly if they differ from defaults:
    python scripts/setup-content-understanding.py \\
        --gpt-deployment gpt-41 \\
        --embedding-deployment text-embedding-3-large

Based on: https://github.com/Azure-Samples/azure-ai-content-understanding-python
"""
import argparse
import json
import logging
import os
import sys

# Allow importing from backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential

# Add backend to path so we can reuse the client
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "app", "services"))
from content_understanding_client import ContentUnderstandingClient

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

ANALYZER_ID = "customsDeclaration"
ANALYZER_SCHEMA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "infrastructure", "customs-analyzer.json"
)


def token_provider() -> str:
    cred = DefaultAzureCredential(
        exclude_managed_identity_credential=True,
        exclude_shared_token_cache_credential=True,
    )
    return cred.get_token("https://cognitiveservices.azure.com/.default").token


def main():
    parser = argparse.ArgumentParser(description="Setup Content Understanding analyzer")
    parser.add_argument(
        "--endpoint",
        default=os.getenv("AZURE_CONTENT_UNDERSTANDING_ENDPOINT"),
        help="Content Understanding endpoint (default: from env)",
    )
    parser.add_argument(
        "--gpt-deployment",
        default=os.getenv("GPT_4_1_DEPLOYMENT", "gpt-4.1"),
        help="GPT-4.1 deployment name (default: gpt-4.1)",
    )
    parser.add_argument(
        "--embedding-deployment",
        default=os.getenv("TEXT_EMBEDDING_3_LARGE_DEPLOYMENT", "text-embedding-3-large"),
        help="text-embedding-3-large deployment name (default: text-embedding-3-large)",
    )
    parser.add_argument(
        "--analyzer-id",
        default=ANALYZER_ID,
        help=f"Analyzer ID to create (default: {ANALYZER_ID})",
    )
    parser.add_argument(
        "--schema",
        default=ANALYZER_SCHEMA_PATH,
        help="Path to analyzer schema JSON",
    )
    parser.add_argument("--skip-defaults", action="store_true", help="Skip setting model defaults")
    parser.add_argument("--delete-first", action="store_true", help="Delete existing analyzer before creating")
    parser.add_argument("--api-key", default=os.getenv("AZURE_CONTENT_UNDERSTANDING_KEY"), help="API key (optional)")

    args = parser.parse_args()

    if not args.endpoint:
        log.error("No endpoint specified. Set AZURE_CONTENT_UNDERSTANDING_ENDPOINT or use --endpoint")
        sys.exit(1)

    # Build client
    client = ContentUnderstandingClient(
        endpoint=args.endpoint,
        subscription_key=args.api_key if args.api_key else None,
        token_provider=token_provider if not args.api_key else None,
    )
    log.info(f"✅ Client created for {args.endpoint}")

    # ── Step 1: Set model deployment defaults ─────────────────────
    if not args.skip_defaults:
        log.info("")
        log.info("📋 Step 1: Setting model deployment defaults...")
        try:
            result = client.update_defaults({
                "gpt-4.1": args.gpt_deployment,
                "text-embedding-3-large": args.embedding_deployment,
            })
            log.info("   Model mappings:")
            for model, deployment in result.get("modelDeployments", {}).items():
                log.info(f"     {model} → {deployment}")
            log.info("   ✅ Defaults configured")
        except Exception as e:
            log.error(f"   ❌ Failed to set defaults: {e}")
            log.error("   Make sure your deployment names match what's in Azure AI Foundry")
            sys.exit(1)
    else:
        log.info("\n⏭️  Skipping defaults (--skip-defaults)")

    # ── Step 2: Create the analyzer ───────────────────────────────
    log.info("")
    log.info(f"📋 Step 2: Creating analyzer '{args.analyzer_id}'...")

    # Load schema
    schema_path = os.path.abspath(args.schema)
    if not os.path.exists(schema_path):
        log.error(f"   Schema file not found: {schema_path}")
        sys.exit(1)

    with open(schema_path) as f:
        analyzer_template = json.load(f)

    # Update the completion model in the schema to match the deployment name
    if "models" in analyzer_template:
        analyzer_template["models"]["completion"] = args.gpt_deployment

    log.info(f"   Schema: {schema_path}")
    log.info(f"   Base analyzer: {analyzer_template.get('baseAnalyzerId')}")
    log.info(f"   Fields: {list(analyzer_template.get('fieldSchema', {}).get('fields', {}).keys())}")

    # Check if analyzer already exists
    try:
        existing = client.get_analyzer(args.analyzer_id)
        status = existing.get("status", "unknown")
        log.info(f"   Analyzer '{args.analyzer_id}' already exists (status: {status})")
        if not args.delete_first:
            log.info("   Use --delete-first to recreate it")
            log.info("")
            log.info("✅ Setup complete — analyzer already exists")
            return
        else:
            log.info("   Deleting existing analyzer...")
            client.delete_analyzer(args.analyzer_id)
            log.info("   ✅ Deleted")
    except Exception:
        log.info(f"   Analyzer '{args.analyzer_id}' does not exist yet — creating...")

    # Create the analyzer
    try:
        response = client.begin_create_analyzer(args.analyzer_id, analyzer_template)
        log.info("   ⏳ Waiting for analyzer creation to complete...")
        client.poll_result(response, timeout_seconds=300)
        log.info(f"   ✅ Analyzer '{args.analyzer_id}' created successfully!")
    except Exception as e:
        log.error(f"   ❌ Failed to create analyzer: {e}")
        log.error("")
        log.error("   Common fixes:")
        log.error("   1. Check that gpt-4.1 and text-embedding-3-large models are deployed")
        log.error("   2. Ensure you have 'Cognitive Services User' role on the resource")
        log.error("   3. Try a different region if you get persistent 500 errors")
        sys.exit(1)

    log.info("")
    log.info("✅ Setup complete!")
    log.info("")
    log.info("Next steps:")
    log.info(f"  1. Set in backend/.env:  AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID={args.analyzer_id}")
    log.info("  2. Restart the backend:  ./scripts/local-dev.sh")


if __name__ == "__main__":
    # Load .env from backend/ if it exists
    env_path = os.path.join(os.path.dirname(__file__), "..", "backend", ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
        log.info(f"Loaded environment from {env_path}")

    main()
