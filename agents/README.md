# Customs Compliance Agents

This directory contains the customs compliance agents built using Microsoft Agent Framework with **persistent agents in Azure AI Foundry**. These agents are created and managed in your Azure AI Foundry project, visible in the portal, and can be reused across multiple workflow runs.

## Key Feature: Persistent Foundry Agents

Unlike ephemeral agents that only exist during code execution, this implementation creates **real agents in Azure AI Foundry** using the `AIProjectClient`. This means:

- ✅ Agents are **visible in the Azure AI Foundry portal**
- ✅ Agents **persist** between workflow runs
- ✅ Agents can be **managed, monitored, and updated** via the portal
- ✅ Agents can be **reused** by other applications using their IDs
- ✅ Agent conversation **threads are managed** by the service

## Overview

The compliance workflow orchestrates 7 specialized agents to analyze customs declarations:

| Agent | Purpose | Model | Tools |
|-------|---------|-------|-------|
| Document Consistency | Cross-field validation, contradiction detection | gpt-4o-mini | - |
| HS Code Validation | Validate and verify HS codes | gpt-4o | HS Code lookup |
| Country Restrictions | Sanctions screening (OFSI UK Sanctions List) | gpt-4o | Sanctions search |
| Country of Origin | Origin plausibility, transshipment detection | gpt-4o | - |
| Controlled Goods | Dual-use/export control screening | gpt-4o | - |
| Value Reasonableness | Declared value analysis | gpt-4o-mini | - |
| Shipper Verification | Shipper information completeness | gpt-4o-mini | - |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                  Azure AI Foundry Project                            │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  PERSISTENT AGENTS (visible in portal)                         │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐              │ │
│  │  │HS Code Agent│ │Country Rest │ │Origin Agent │  ... (x7)    │ │
│  │  │ ID: abc123  │ │ ID: def456  │ │ ID: ghi789  │              │ │
│  │  └─────────────┘ └─────────────┘ └─────────────┘              │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Local Workflow (workflow.py)                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  DeclarationDispatcher (fan-out)                              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│     ┌────────────────────────┼────────────────────────┐             │
│     ▼            ▼           ▼           ▼            ▼             │
│ ┌────────┐ ┌──────────┐ ┌─────────┐ ┌──────────┐ ┌─────────┐        │
│ │HS Code │ │ Country  │ │ Origin  │ │Controlled│ │  Value  │  ...   │
│ │Executor│ │ Executor │ │ Executor│ │ Executor │ │Executor │        │
│ └────────┘ └──────────┘ └─────────┘ └──────────┘ └─────────┘        │
│     │            │           │           │            │             │
│     └────────────┴───────────┼───────────┴────────────┘             │
│                              ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  ComplianceResultAggregator (fan-in)                          │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## Files

```
agents/
├── __init__.py                      # Module exports
├── README.md                        # This file
├── .foundry_agent_ids.json          # Saved agent IDs (auto-generated)
├── compliance-workflow.yaml         # Declarative workflow definition
├── workflow.py                      # Python workflow with Foundry agents
├── tools.py                         # Function tools for CosmosDB
├── container.py                     # Container entry point
├── test_local.py                    # Local testing utilities
│
├── document-consistency-agent.yaml  # Agent definitions
├── hs-code-validation-agent.yaml
├── country-restrictions-agent.yaml
├── country-of-origin-agent.yaml
├── controlled-goods-agent.yaml
├── value-reasonableness-agent.yaml
└── shipper-verification-agent.yaml
```

## Requirements

```bash
# Install dependencies (--pre flag required for preview packages)
pip install agent-framework-azure-ai --pre
pip install azure-ai-projects azure-identity pydantic pyyaml
```

## Environment Variables

```bash
# Required for Azure AI Foundry
export AZURE_AI_PROJECT_ENDPOINT="https://<your-project>.services.ai.azure.com/api/projects/<project-id>"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o"

# Required for CosmosDB reference data
export AZURE_COSMOS_ENDPOINT="https://your-cosmos.documents.azure.com:443/"
export AZURE_COSMOS_KEY="your-key"
export AZURE_COSMOS_DATABASE="customsdb"
```

## Quick Start

### 1. Login to Azure

```bash
az login
```

### 2. Create Agents in Azure AI Foundry

```bash
# Create all 7 compliance agents in your Foundry project
python agents/workflow.py --create
```

This creates persistent agents and saves their IDs to `.foundry_agent_ids.json`.

### 3. View Agents in Portal

Open the [Azure AI Foundry portal](https://ai.azure.com) and navigate to your project. You'll see all 7 agents listed under the Agents section!

### 4. Run Compliance Check

```bash
# Run workflow using the persistent agents
python agents/workflow.py --run
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `python workflow.py --create` | Create agents in Azure AI Foundry |
| `python workflow.py --run` | Run compliance check with sample data |
| `python workflow.py --list` | List all agents in your Foundry project |
| `python workflow.py --cleanup` | Delete agents from Foundry |
| `python workflow.py --recreate` | Delete and recreate all agents |

## Local Testing (without Foundry)

For testing without Azure AI Foundry:

```bash
python agents/test_local.py --interactive
```

```bash
python agents/test_local.py --sample suspicious_origin
```

### Interactive mode

```bash
python agents/test_local.py --interactive
```

### List available samples

```bash
python agents/test_local.py --list
```

## Environment Variables

Required in `.env`:

```env
AZURE_OPENAI_ENDPOINT=https://your-openai.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=gpt-41
AZURE_COSMOS_DB_ENDPOINT=https://your-cosmos.documents.azure.com:443/
AZURE_COSMOS_DB_KEY=your-key
AZURE_COSMOS_DB_DATABASE=customsdb
```

## Usage in Code

```python
from agents import run_compliance_check

report = await run_compliance_check({
    "shipper": "Acme Electronics Ltd, Shenzhen, China",
    "receiver": "UK Import Co, London, UK",
    "goods_description": "LED Computer Monitors",
    "hs_code": "852852",
    "declared_value": "USD 15000",
    "country_of_origin": "China",
    "destination_country": "United Kingdom",
    "weight": "150 kg",
    "quantity": "50 units",
})

print(f"Risk Level: {report.overall_risk}")
print(f"Findings: {report.total_findings}")
print(f"Manual Review: {report.requires_manual_review}")
```

## Tools (Functions)

### HS Code Tools

| Tool | Description |
|------|-------------|
| `lookup_hs_code` | Look up HS code in UK Tariff database |
| `search_hs_codes_by_description` | Search codes by goods description |
| `validate_hs_code_format` | Validate HS code format |
| `find_similar_hs_codes` | Find codes with similar prefixes |

### Sanctions Tools

| Tool | Description |
|------|-------------|
| `search_sanctions_by_name` | Search OFSI UK Sanctions List by name |
| `search_sanctions_by_country` | Search sanctions by country |
| `check_entity_sanctions` | Comprehensive entity screening |
| `get_sanctions_regimes` | Get active sanctions regime statistics |

## Deployment to Azure AI Foundry

### Using VS Code AI Toolkit

1. Install the Azure AI Toolkit extension
2. Open the workflow.yaml file
3. Right-click and select "Deploy Agent"

### Using Azure CLI

```bash
# Build container
docker build -t customs-compliance-agent:latest -f agents.Dockerfile .

# Push to Azure Container Registry
az acr login --name <your-acr>
docker tag customs-compliance-agent:latest <your-acr>.azurecr.io/customs-compliance-agent:latest
docker push <your-acr>.azurecr.io/customs-compliance-agent:latest

# Deploy to Foundry Agent Service
az ai foundry agent create \
  --name "CustomsComplianceAgent" \
  --image <your-acr>.azurecr.io/customs-compliance-agent:latest \
  --resource-group <rg> \
  --workspace <workspace>
```

## Observability

The workflow enables OpenTelemetry tracing for visualization in VS Code:

```python
from agent_framework.observability import setup_observability

# Enable VS Code AI Toolkit trace visualization
setup_observability(vs_code_extension_port=4319)
```

Open the AI Toolkit trace viewer in VS Code to see the workflow execution.

## Output Structure

```json
{
  "declaration_id": "decl-20241215123456",
  "timestamp": "2024-12-15T12:34:56.789Z",
  "overall_risk": "high",
  "requires_manual_review": true,
  "total_findings": 5,
  "critical_count": 1,
  "high_count": 2,
  "medium_count": 1,
  "low_count": 1,
  "info_count": 0,
  "agent_results": [
    {
      "agent_name": "HSCodeValidationAgent",
      "findings": [...],
      "processing_time_ms": 1234
    }
  ],
  "processing_time_ms": 5678
}
```

## Risk Levels

| Level | Criteria |
|-------|----------|
| `critical` | Any critical findings |
| `high` | Any high severity findings |
| `medium` | Multiple medium findings |
| `low` | Some low/medium findings |
| `clear` | No significant findings |
