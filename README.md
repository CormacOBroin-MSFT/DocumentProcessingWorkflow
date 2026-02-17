# Autonomous Document Workflow

AI-powered customs document processing workflow using Azure AI services. Upload a customs declaration, extract structured data with OCR, then run multi-agent compliance validation — all orchestrated through Azure AI Foundry.

![Azure](https://img.shields.io/badge/Azure-App%20Service-blue) ![React](https://img.shields.io/badge/React-19-61dafb) ![Flask](https://img.shields.io/badge/Flask-3.0-green) ![TypeScript](https://img.shields.io/badge/TypeScript-5.7-blue)

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    Azure App Service                        │
│  ┌──────────────────┐      ┌──────────────────┐           │
│  │   React SPA      │      │    Flask API     │           │
│  │   (static)       │ ───► │    /api/*        │           │
│  └──────────────────┘      └────────┬─────────┘           │
└─────────────────────────────────────┼──────────────────────┘
                                      │ Managed Identity
    ┌──────────────┬──────────────────┼──────────────────┬───────────────┐
    ▼              ▼                  ▼                  ▼               ▼
┌────────┐  ┌───────────┐   ┌──────────────┐   ┌──────────────┐  ┌──────────┐
│  Blob  │  │  Content  │   │   Azure AI   │   │   Azure AI   │  │ Cosmos   │
│Storage │  │Understanding  │   Foundry    │   │    Search   │  │   DB     │
│        │  │(custom     │   │(7 agents +  │   │(HS codes,  │  │          │
│        │  │ analyzer)  │   │ workflow)   │   │ sanctions) │  │          │
└────────┘  └───────────┘   └──────────────┘   └──────────────┘  └──────────┘
```

### Processing Pipeline

1. **Upload** — Document uploaded to Azure Blob Storage (identity-based auth, no SAS tokens)
2. **OCR + Extraction** — Azure Content Understanding with custom analyzer extracts 7 customs fields
3. **Transform** — LLM enriches/validates extracted data
4. **Compliance** — 7 specialist AI agents run sequentially via Azure AI Foundry workflow
5. **Review** — Human-in-the-loop approval with confidence scoring
6. **Store** — Approved declaration saved to Cosmos DB

---

## Getting Started

### Prerequisites

- **Node.js 20+** (recommend `nvm install 22`)
- **Python 3.12+**
- **Azure CLI** — `az login` before running anything
- An Azure subscription

### Step 1: Run the Setup Script

The setup script provisions all Azure infrastructure, configures RBAC, indexes reference data, creates agents, and generates your `.env` file.

```bash
./scripts/setup-azure.sh
```

This creates:
- Azure Storage Account (with Blob container)
- Azure AI Services (Foundry hub + project, OpenAI model deployments)
- Azure AI Search (HS code + sanctions indexes)
- Azure Cosmos DB (NoSQL)
- Bing Grounding resource + connection
- Content Understanding custom analyzer
- All 7 specialist compliance agents in Foundry
- `backend/.env` with all endpoints pre-configured

> **Note:** The script is idempotent — safe to re-run. It skips resources that already exist.

### Step 2: Create the Compliance Workflow in Foundry (Manual)

The setup script creates all 8 agents but the **workflow** must be pasted manually in the Foundry portal.

1. Go to [Azure AI Foundry](https://ai.azure.com) → your project → **Agents**.
2. Click **+ New agent** → choose **Workflow**.
3. Set the **Name** to exactly: `customs-compliance-workflow`
4. Switch to the **YAML editor**.
5. Paste the entire contents of [`agents/compliance-workflow.yaml`](agents/compliance-workflow.yaml).
6. **Save** the workflow.

> The workflow references each agent by name (e.g. `DocumentConsistencyAgent`). All 8 agents from Step 1 must exist before the workflow will run.

### Step 3: Verify the Content Understanding Analyzer (If Needed)

The setup script attempts to create a custom CU analyzer via the API. If it succeeded, you're done — skip this step.

If the script logged a warning about analyzer creation, create it manually:

1. Go to [Content Understanding Studio](https://ai.azure.com/contentunderstanding) and sign in.
2. Select the Content Understanding resource created by the script (endpoint is in `backend/.env`).
3. **Create a new project** with kind **Extract**.
4. **Add these 7 fields:**

   | Field Name         | Type   | Method  | Description                        |
   |--------------------|--------|---------|------------------------------------|
   | `shipper`          | string | extract | Shipper / exporter name            |
   | `receiver`         | string | extract | Receiver / importer name           |
   | `goodsDescription` | string | extract | Description of goods               |
   | `value`            | string | extract | Total declared value               |
   | `countryOfOrigin`  | string | extract | Country of origin (ISO or name)    |
   | `hsCode`           | string | extract | Harmonized System code             |
   | `weight`           | string | extract | Weight / quantity                   |

5. **Deploy** the analyzer and update `AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID` in `backend/.env` with the analyzer name.

> The field schema is also in [`infrastructure/customs-analyzer.json`](infrastructure/customs-analyzer.json) for reference.

### Step 4: Run Locally

```bash
./scripts/local-dev.sh
```

This starts:
- **Frontend** → http://localhost:5173
- **Backend** → http://localhost:5000

Open the frontend, upload a sample invoice from [`SampleInvoices/`](SampleInvoices/), and click through the workflow.

---

## Project Structure

```
DocumentProcessingWorkflow/
├── src/                          # React frontend (TypeScript)
│   ├── App.tsx                   # Main application
│   ├── components/               # UI components
│   ├── hooks/                    # Custom React hooks
│   └── api/                      # Backend API client
├── backend/                      # Flask backend (Python)
│   ├── app/
│   │   ├── routes/              # API endpoints
│   │   └── services/            # Azure service clients
│   ├── .env.example             # Sample environment variables
│   └── run.py                   # Entry point
├── agents/                       # AI Foundry compliance agents
│   ├── compliance-workflow.yaml # Declarative workflow YAML (paste into Foundry)
│   ├── workflow.py              # Agent management CLI
│   ├── tools.py                 # Agent tool definitions
│   └── *.yaml                   # Individual agent definitions
├── infrastructure/               # Azure IaC
│   ├── customs-analyzer.json    # CU analyzer field schema reference
│   └── local-dev.bicep          # Bicep template
├── scripts/                      # Shell scripts
│   ├── setup-azure.sh           # Full Azure provisioning (run first)
│   ├── local-dev.sh             # Start frontend + backend
│   ├── deploy.sh                # App Service deployment
│   └── cleanup-azure.sh         # Teardown all resources
├── StaticDataForAgents/          # Reference data (HS codes, sanctions CSVs)
├── SampleInvoices/               # Test documents
├── Dockerfile                    # Container build
└── README.md
```

---

## Compliance Agents

The workflow runs 7 specialist agents sequentially, then an aggregator combines their findings:

| Agent | Purpose | Tools |
|-------|---------|-------|
| `DocumentConsistencyAgent` | Cross-checks field consistency | — |
| `HSCodeValidationAgent` | Validates HS codes against UK tariff | Azure AI Search (`hs-codes`) |
| `CountryRestrictionsAgent` | Checks sanctions/embargoes | Azure AI Search (`sanctions`) |
| `CountryOfOriginAgent` | Validates origin country plausibility | — |
| `ControlledGoodsAgent` | Screens for dual-use/controlled items | — |
| `ValueReasonablenessAgent` | Checks declared value reasonableness | — |
| `ShipperVerificationAgent` | Verifies shipper identity | AI Search + Bing Grounding |
| `ComplianceAggregatorAgent` | Combines all findings into ComplianceReport | — |

Agent definitions are in [`agents/*.yaml`](agents/). The orchestration workflow is in [`agents/compliance-workflow.yaml`](agents/compliance-workflow.yaml).

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/upload` | POST | Upload document to Azure Blob Storage |
| `/api/ocr/analyze` | POST | Extract fields via Content Understanding |
| `/api/transform/structure` | POST | LLM data transformation + enrichment |
| `/api/compliance/validate` | POST | Multi-agent compliance validation |
| `/api/cosmosdb/declarations` | GET/POST | Cosmos DB declaration CRUD |

---

## Environment Variables

Generated automatically by `./scripts/setup-azure.sh` into `backend/.env`. All Azure services use `DefaultAzureCredential` — no API keys in code.

Key variables:

| Variable | Description |
|----------|-------------|
| `AZURE_STORAGE_CONNECTION_STRING` | Storage account connection string |
| `AZURE_CONTENT_UNDERSTANDING_ENDPOINT` | CU resource endpoint |
| `AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID` | Custom analyzer name (e.g. `customsDeclaration`) |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint |
| `AZURE_OPENAI_DEPLOYMENT` | Model deployment name (e.g. `gpt-4.1`) |
| `AZURE_AI_PROJECT_ENDPOINT` | Foundry project endpoint (for workflow) |
| `AZURE_COSMOS_ENDPOINT` | Cosmos DB endpoint |

See `backend/.env.example` for the full list.

---

## Security

- **Managed Identity / DefaultAzureCredential** — No API keys in code or config
- **No SAS tokens** — Blob access via RBAC role assignments
- **HTTPS only** — TLS enforced on App Service
- **RBAC** — Least-privilege access to all Azure resources

---

## Troubleshooting

### Content Understanding returns `ContentSourceNotAccessible`
The CU resource's managed identity needs `Storage Blob Data Reader` on the storage account. The setup script assigns this, but RBAC can take 5–10 minutes to propagate.

### Compliance check fails with "AZURE_AI_PROJECT_ENDPOINT not set"
Re-run `./scripts/setup-azure.sh` — it adds the endpoint to `backend/.env`.

### Backend can't authenticate to Azure services
Run `az login` and ensure your account has the required roles (the setup script assigns them).

### Storage uploads fail
Azure Policy can re-disable public network access on storage accounts. Re-run `./scripts/setup-azure.sh` to restore it.

### View App Service Logs (production)
```bash
az webapp log tail --name <app-name> --resource-group <rg-name>
```

---

## License

MIT License - See [LICENSE.txt](LICENSE.txt)
