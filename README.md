# Autonomous Document Workflow

AI-powered customs document processing workflow using Azure AI services. This application showcases an agentic AI workflow for processing customs declarations with OCR, data transformation, and multi-agent compliance validation.

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

## Features

- **Document Upload** — Drag & drop document intake with Azure Blob Storage
- **OCR + Field Extraction** — Azure Content Understanding with a custom analyzer
- **LLM Transformation** — Azure OpenAI enriches and validates extracted data
- **Multi-Agent Compliance** — 7 specialist agents run sequentially via Azure AI Foundry workflow
- **Human-in-the-Loop** — Manual review and approval with per-field confidence scoring
- **Audit Trail** — Approved declarations persisted to Azure Cosmos DB

---

## Prerequisites

- **Node.js 20+** (recommend `nvm install 22`)
- **Python 3.12+**
- **Azure CLI** (`az login` for local development)
- An Azure subscription with the following resources provisioned (see [Azure Setup](#azure-setup))

---

## Azure Setup

All services authenticate via **`DefaultAzureCredential`** — no API keys are stored in code or config. For local development, `az login` is sufficient.

### 1. Azure Blob Storage

Create a storage account with a container (e.g. `customs-documents`). Disable key-based access if desired — the app uses identity-based auth.

### 2. Azure Content Understanding (Custom Analyzer) — **Manual Step Required**

> **The custom analyzer must be created manually in Azure AI Content Understanding Studio.**
> The analyzer creation API is not used — the Studio UI is the supported path.

#### Steps

1. Go to [Content Understanding Studio](https://ai.azure.com/contentunderstanding) and sign in.
2. **Create a new Content Understanding resource** (or use an existing one). Note the endpoint URL.
3. **Create a new project** with kind **Extract**.
4. **Add the following 7 fields** to match the customs schema:

   | Field Name         | Type   | Method  | Description                        |
   |--------------------|--------|---------|------------------------------------|
   | `shipper`          | string | extract | Shipper / exporter name            |
   | `receiver`         | string | extract | Receiver / importer name           |
   | `goodsDescription` | string | extract | Description of goods               |
   | `value`            | string | extract | Total declared value               |
   | `countryOfOrigin`  | string | generate | Country of origin (ISO or name)   |
   | `hsCode`           | string | extract | Harmonized System code             |
   | `weight`           | string | extract | Weight / quantity                   |

   > **Tip:** Upload a sample invoice to test extraction quality. The `generate` method on `countryOfOrigin` lets the model infer the country from context (addresses, etc.) when it isn't explicitly stated.

5. **Deploy the analyzer** and note the analyzer name (e.g. `CustomsCU`).

The field schema is also documented in [infrastructure/customs-analyzer.json](infrastructure/customs-analyzer.json).

#### RBAC for Content Understanding

The CU resource's **system-assigned managed identity** needs read access to your storage account so it can access uploaded blobs:

```bash
# Get the CU resource's managed identity principal ID
CU_PRINCIPAL_ID=$(az cognitiveservices account identity show \
  --name <cu-resource-name> \
  --resource-group <cu-resource-group> \
  --query principalId -o tsv)

# Get storage account resource ID
STORAGE_ID=$(az storage account show \
  --name <storage-account-name> \
  --resource-group <storage-resource-group> \
  --query id -o tsv)

# Assign Storage Blob Data Reader
az role assignment create \
  --assignee-object-id "$CU_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Reader" \
  --scope "$STORAGE_ID"
```

> **Note:** RBAC role assignments can take 5–10 minutes to propagate. If you get `ContentSourceNotAccessible` errors, wait and retry.

### 3. Azure OpenAI

Deploy a model (e.g. `gpt-4o`) in Azure OpenAI Service. The endpoint and deployment name are configured via environment variables.

### 4. Azure AI Foundry (Compliance Agents & Workflow) — **Manual Steps Required**

The compliance workflow uses 8 agents orchestrated by a declarative YAML workflow, all managed in Azure AI Foundry.

#### 4a. Create the AI Foundry Hub & Project

1. Go to [Azure AI Foundry](https://ai.azure.com) and sign in.
2. Create a **Hub** (or use an existing one).
3. Create a **Project** inside the hub.
4. Note the **Project endpoint** — it looks like:
   ```
   https://<hub-name>.services.ai.azure.com/api/projects/<project-name>
   ```
5. Deploy a model (e.g. `gpt-41-mini`) under the project's **Model deployments**.

#### 4b. Create Each Agent

Create 8 agents in the Foundry portal. Each agent's YAML definition is in the [agents/](agents/) directory — copy the `instructions` and `model` from each file:

| Agent Name                  | YAML File                              | Tools                          |
|-----------------------------|----------------------------------------|--------------------------------|
| `DocumentConsistencyAgent`  | `document-consistency-agent.yaml`      | None                           |
| `HSCodeValidationAgent`     | `hs-code-validation-agent.yaml`        | Azure AI Search (`hs-codes`)   |
| `CountryRestrictionsAgent`  | `country-restrictions-agent.yaml`      | Azure AI Search (`sanctions`)  |
| `CountryOfOriginAgent`      | `country-of-origin-agent.yaml`         | None                           |
| `ControlledGoodsAgent`      | `controlled-goods-agent.yaml`          | None                           |
| `ValueReasonablenessAgent`  | `value-reasonableness-agent.yaml`      | None                           |
| `ShipperVerificationAgent`  | `shipper-verification-agent.yaml`      | AI Search + Bing Grounding     |
| `ComplianceAggregatorAgent` | `compliance-aggregator-agent.yaml`     | None                           |

For each agent:
1. In your Foundry project, go to **Agents** → **+ New agent**.
2. Set the **Name** exactly as shown above (the workflow references these names).
3. Set the **Model** to your deployed model (e.g. `gpt-41-mini`).
4. Paste the `instructions` from the corresponding YAML file.
5. If the agent uses tools (AI Search / Bing), add them under the agent's **Tools** tab and configure the connection.

Alternatively, use the CLI to create agents programmatically:
```bash
cd agents
python workflow.py --create      # Create all 8 agents
python workflow.py --list         # Verify they exist
python workflow.py --recreate     # Delete and recreate all
```

#### 4c. Create the Workflow — **Copy/Paste YAML**

1. In your Foundry project, go to **Agents** → **+ New agent** → choose **Workflow**.
2. Set the **Name** to `customs-compliance-workflow`.
3. Switch to the **YAML editor** and paste the entire contents of [agents/compliance-workflow.yaml](agents/compliance-workflow.yaml).
4. **Save** the workflow.

> **Important:** The workflow YAML references agents by name (e.g. `DocumentConsistencyAgent`). All 8 agents from step 4b must exist before the workflow can run.

### 5. Azure AI Search

Provision an Azure AI Search resource for HS code validation and sanctions list lookups. Index the reference data from [StaticDataForAgents/](StaticDataForAgents/).

### 6. Azure Cosmos DB

Create a Cosmos DB account (NoSQL API) with a database and container for storing approved customs declarations.

---

## Local Development

### Quick Start

**Terminal 1 — Frontend:**
```bash
npm install
npm run dev
```
→ http://localhost:5173

**Terminal 2 — Backend:**
```bash
cd backend
cp .env.example .env   # Edit with your Azure resource values
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
az login                  # Required for DefaultAzureCredential
python run.py
```
→ http://localhost:5000

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
│   ├── workflow.py              # Agent workflow runner
│   ├── tools.py                 # Agent tool definitions
│   └── *.yaml                   # Agent definitions
├── infrastructure/               # Azure IaC
│   ├── customs-analyzer.json    # CU analyzer field schema reference
│   └── app-service.bicep        # Bicep template
├── scripts/                      # Shell scripts
│   ├── deploy.sh                # App deployment
│   ├── setup-azure.sh           # Azure resource provisioning
│   └── cleanup-azure.sh         # Teardown
├── StaticDataForAgents/          # Reference data (HS codes, sanctions)
├── SampleInvoices/               # Test documents
├── Dockerfile                    # Container build
└── README.md
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/storage/upload` | POST | Upload document to Azure Blob Storage |
| `/api/ocr/analyze` | POST | Extract fields via Content Understanding |
| `/api/transform/structure` | POST | LLM data transformation + enrichment |
| `/api/compliance/validate` | POST | Multi-agent compliance validation |
| `/api/cosmosdb/declarations` | GET/POST | Cosmos DB declaration CRUD |

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in your values. All Azure services use `DefaultAzureCredential` — no API keys required (except where noted).

```env
# ── Azure Blob Storage ──
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
AZURE_STORAGE_CONTAINER=customs-documents

# ── Azure Content Understanding ──
# Custom analyzer MUST be created manually in CU Studio (see README)
AZURE_CONTENT_UNDERSTANDING_ENDPOINT=https://<cu-resource>.cognitiveservices.azure.com/
AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID=CustomsCU

# ── Azure OpenAI (for Transform step) ──
AZURE_OPENAI_ENDPOINT=https://<openai-resource>.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o

# ── Azure AI Search (for compliance agents) ──
AZURE_AI_SEARCH_ENDPOINT=https://<search-resource>.search.windows.net
AZURE_AI_SEARCH_INDEX_HS=hs-codes-index
AZURE_AI_SEARCH_INDEX_SANCTIONS=sanctions-index

# ── Azure Cosmos DB ──
AZURE_COSMOS_ENDPOINT=https://<cosmos-account>.documents.azure.com:443/
AZURE_COSMOS_DATABASE=customs-db
AZURE_COSMOS_CONTAINER=declarations

# ── Azure AI Foundry (Compliance Workflow) ──
AZURE_AI_PROJECT_ENDPOINT=https://<foundry-hub>.services.ai.azure.com/api/projects/<project>
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4.1

# ── Bing Grounding (optional, for agent web search) ──
BING_GROUNDING_CONNECTION_NAME=bing-grounding

# ── Flask ──
FLASK_ENV=development
FLASK_DEBUG=True
```

---

## Security

- **Managed Identity / DefaultAzureCredential** — No API keys in code or config
- **No SAS tokens** — Blob access via RBAC role assignments (Storage Blob Data Reader)
- **HTTPS only** — TLS enforced on App Service
- **RBAC** — Least-privilege access to all Azure resources

---

## Troubleshooting

### Content Understanding returns `ContentSourceNotAccessible`
The CU resource's managed identity doesn't have read access to blob storage, or the RBAC assignment hasn't propagated yet (5–10 min). Verify the role assignment:
```bash
az role assignment list --scope <storage-resource-id> --query "[?principalId=='<cu-principal-id>']"
```

### Compliance check fails with "AZURE_AI_PROJECT_ENDPOINT not set"
Add `AZURE_AI_PROJECT_ENDPOINT` to your `backend/.env`. This is the full Foundry project endpoint URL.

### Backend can't authenticate to Azure services
Ensure you've run `az login` and your account has the required roles on each resource (Contributor, Cognitive Services User, Storage Blob Data Contributor, etc.).

### View App Service Logs (production)
```bash
az webapp log tail --name <app-name> --resource-group <rg-name>
```

---

## License

MIT License - See [LICENSE.txt](LICENSE.txt)
