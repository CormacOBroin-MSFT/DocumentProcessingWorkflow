# Autonomous Document Workflow

AI-powered customs document processing workflow using Azure AI services. This application showcases an agentic AI workflow for processing customs declarations with OCR, data transformation, and compliance validation.

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
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
       ┌───────────┐          ┌───────────┐           ┌───────────┐
       │   Blob    │          │  Content  │           │  Azure    │
       │  Storage  │          │ Understand│           │  OpenAI   │
       │           │          │ ing       │           │           │
       └───────────┘          └───────────┘           └───────────┘
```

**Single App Service hosts both frontend and backend** - simple, cost-effective, easy to manage.

## Features

- 📄 **Document Upload** - Drag & drop document intake
- ☁️ **Azure Blob Storage** - Secure cloud document storage  
- 🔍 **OCR Processing** - Azure AI Content Understanding for text extraction
- 🔄 **Data Transformation** - LLM-powered structuring of extracted data
- ✅ **Compliance Validation** - Automated customs compliance checks
- 👤 **Human-in-the-Loop** - Manual review and approval workflow
- 📊 **Confidence Scoring** - Real-time accuracy metrics at each stage

---

## Local Development

### Prerequisites

- Node.js 20+ (recommend using `nvm install 22`)
- Python 3.9+
- Azure account (optional - works with mock data)

### Quick Start

**Terminal 1 - Frontend:**
```bash
npm install
npm run dev
```
→ http://localhost:5173

**Terminal 2 - Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python run.py
```
→ http://localhost:5000

### Mock Mode

Without Azure credentials, the app runs in mock mode with sample data - you'll see a yellow warning banner but can demo the full workflow.

---

## Azure Deployment

### One-Click Deploy

```bash
# 1. Login to Azure
az login

# 2. Run deployment script
chmod +x deploy.sh
./deploy.sh
```

This creates all resources with proper Managed Identity configuration:
- **App Service Plan** (B1 - ~$13/month)
- **App Service** (Linux Python 3.11)
- **Storage Account** + blob container
- **Content Understanding** (F0 free tier)
- **Key Vault** for secrets

### Post-Deployment: Add OpenAI Key

```bash
az keyvault secret set \
  --vault-name autonomousflow-kv \
  --name OPENAI-API-KEY \
  --value "sk-your-key-here"
```

### CI/CD with GitHub Actions

Push to `main` branch auto-deploys via GitHub Actions. Setup required secrets:

1. Create a service principal:
```bash
az ad sp create-for-rbac --name "autonomousflow-deploy" \
  --role contributor \
  --scopes /subscriptions/{subscription-id}/resourceGroups/autonomousflow-rg \
  --sdk-auth
```

2. Add the JSON output as `AZURE_CREDENTIALS` secret in GitHub repo settings.

---

## Project Structure

```
AutonomousFlow/
├── src/                          # React frontend
│   ├── App.tsx                   # Main application
│   ├── components/ui/            # UI components
│   └── lib/                      # Utilities
├── backend/                      # Flask backend
│   ├── app/
│   │   ├── __init__.py          # App factory (serves static + API)
│   │   ├── routes/              # API endpoints
│   │   └── services/            # Azure service clients
│   └── run.py                   # Entry point
├── infrastructure/               # Azure IaC
│   └── app-service.bicep        # Bicep template
├── .github/workflows/            # CI/CD
│   └── deploy.yml               # GitHub Actions
├── Dockerfile                    # Container build
├── deploy.sh                     # One-click deploy script
└── README.md
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/documents/upload` | POST | Upload document |
| `/api/storage/upload` | POST | Store in Azure Blob |
| `/api/ocr/analyze` | POST | Run Content Understanding OCR |
| `/api/transform/structure` | POST | LLM data transformation |
| `/api/compliance/validate` | POST | LLM compliance validation |
| `/api/customs/submit` | POST | Submit to customs (mock) |

---

## Environment Variables

### Local Development (`backend/.env`)

```env
# Azure Storage
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;...
AZURE_STORAGE_CONTAINER=customs-documents

# Azure Content Understanding
AZURE_CONTENT_UNDERSTANDING_ENDPOINT=https://xxx.cognitiveservices.azure.com/
# AZURE_CONTENT_UNDERSTANDING_KEY=xxx  (optional - uses DefaultAzureCredential)

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://xxx.openai.azure.com/
AZURE_OPENAI_KEY=xxx
AZURE_OPENAI_DEPLOYMENT=gpt-4o

# Flask
FLASK_ENV=development
FLASK_DEBUG=True
```

### Production (App Service)

Set automatically by Bicep deployment - uses Managed Identity (no keys in code):

| Variable | Description |
|----------|-------------|
| `AZURE_STORAGE_ACCOUNT_NAME` | Storage account name |
| `AZURE_STORAGE_CONTAINER` | Blob container name |
| `AZURE_CONTENT_UNDERSTANDING_ENDPOINT` | Content Understanding URL |
| `AZURE_KEY_VAULT_URL` | Key Vault URL (for OpenAI key) |

---

## Estimated Azure Costs

| Resource | SKU | ~Monthly Cost |
|----------|-----|---------------|
| App Service Plan | B1 | $13 |
| Storage Account | Standard LRS | $1 |
| Content Understanding | F0 (free) → S0 | $0 → $1.50/1K pages |
| Key Vault | Standard | ~$0.03/10K ops |
| **Total** | | **~$15/month** |

*Azure OpenAI billed separately based on token usage*

---

## Security Best Practices

- ✅ **Managed Identity** - No credentials in code or config
- ✅ **Key Vault** - Secure storage for external API keys
- ✅ **HTTPS Only** - TLS enforced on App Service
- ✅ **RBAC** - Least-privilege access to Azure resources
- ✅ **No public blob access** - Storage account locked down

---

## Troubleshooting

### View App Service Logs
```bash
az webapp log tail --name autonomousflow-app --resource-group autonomousflow-rg
```

### SSH into App Service
```bash
az webapp ssh --name autonomousflow-app --resource-group autonomousflow-rg
```

### Restart App Service
```bash
az webapp restart --name autonomousflow-app --resource-group autonomousflow-rg
```

---

## License

MIT License - See [LICENSE.txt](LICENSE.txt)
