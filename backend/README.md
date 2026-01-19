# Flask Backend - AI Document Processing API

A REST API backend for the AI Document Processing demo application, providing secure server-side integration with Azure services and OpenAI.

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────┐
│         React Frontend (TypeScript)      │
│  - UI/UX & Animations                    │
│  - State Management                      │
│  - HTTP Client (fetch)                   │
└─────────────────────────────────────────┘
                    ↓ HTTP/REST
┌─────────────────────────────────────────┐
│         Flask Backend (Python)           │
│  - RESTful API Endpoints                 │
│  - Azure SDK Integration                 │
│  - Secure Credential Management          │
│  - Business Logic & Validation           │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│           Azure Services                 │
│  - Blob Storage (document storage)       │
│  - AI Document Intelligence (OCR)        │
│  - OpenAI (LLM processing)               │
└─────────────────────────────────────────┘
```

## 📂 Project Structure

```
backend/
├── app/
│   ├── __init__.py              # Flask app factory
│   ├── config.py                # Configuration management
│   ├── routes/                  # API endpoint blueprints
│   │   ├── __init__.py
│   │   ├── upload.py           # Document upload endpoint
│   │   ├── storage.py          # Azure Blob Storage endpoints
│   │   ├── ocr.py              # Document Intelligence endpoints
│   │   ├── transform.py        # LLM data transformation
│   │   ├── compliance.py       # LLM compliance validation
│   │   └── customs.py          # Mock customs submission
│   ├── services/               # Azure service integrations
│   │   ├── __init__.py
│   │   ├── azure_blob.py       # Azure Blob Storage client
│   │   ├── azure_doc_intelligence.py  # Document Intelligence client
│   │   └── llm_client.py       # OpenAI LLM client
│   └── models/                 # Data models (Pydantic)
│       ├── __init__.py
│       └── customs.py          # Customs declaration models
├── .env                        # Environment variables (DO NOT COMMIT)
├── .env.example                # Example environment configuration
├── .gitignore                  # Git ignore patterns
├── requirements.txt            # Python dependencies
└── run.py                      # Application entry point
```

## 🚀 Quick Start

### Prerequisites

- Python 3.9 or higher
- pip (Python package manager)
- Azure account with:
  - Azure Storage Account
  - Azure AI Document Intelligence resource
- OpenAI API key

### Installation

1. **Navigate to backend directory**:
   ```bash
   cd backend
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv venv
   
   # Activate on Linux/Mac:
   source venv/bin/activate
   
   # Activate on Windows:
   venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` with your actual credentials:
   ```env
   # Azure Blob Storage
   AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
   AZURE_STORAGE_CONTAINER=customs-documents
   
   # Azure AI Document Intelligence
   AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
   AZURE_DOCUMENT_INTELLIGENCE_KEY=your_key_here
   
   # OpenAI
   OPENAI_API_KEY=sk-...
   OPENAI_MODEL=gpt-4o
   
   # Flask
   FLASK_ENV=development
   FLASK_DEBUG=True
   ```

5. **Run the server**:
   ```bash
   python run.py
   ```
   
   Server will start at `http://localhost:5000`

6. **Test the health endpoint**:
   ```bash
   curl http://localhost:5000/health
   ```

## 📡 API Endpoints

### Health Check

```http
GET /health
```

**Response**:
```json
{
  "status": "healthy",
  "service": "AI Document Processing API",
  "version": "1.0.0"
}
```

---

### 1. Document Upload

```http
POST /api/documents/upload
Content-Type: multipart/form-data
```

**Request**:
- `file`: File (image/PDF)

**Response**:
```json
{
  "document_id": "abc-123-def-456",
  "file_name": "customs-doc.pdf",
  "status": "uploaded"
}
```

---

### 2. Azure Blob Storage Upload

```http
POST /api/storage/upload
Content-Type: multipart/form-data
```

**Request**:
- `file`: File to upload
- `document_id`: UUID (optional)

**Response**:
```json
{
  "document_id": "abc-123-def-456",
  "blob_url": "https://yourstorage.blob.core.windows.net/customs-documents/...",
  "status": "stored"
}
```

---

### 3. OCR Analysis

```http
POST /api/ocr/analyze
Content-Type: application/json
```

**Request**:
```json
{
  "document_id": "abc-123-def-456",
  "blob_url": "https://yourstorage.blob.core.windows.net/..."
}
```

**Response**:
```json
{
  "document_id": "abc-123-def-456",
  "raw_data": {
    "SHIPPER NAME": {
      "value": "Global Electronics Ltd.",
      "confidence": 0.98
    },
    "RECEIVER NAME": {
      "value": "European Distribution Center",
      "confidence": 0.97
    }
  },
  "ocr_confidence": 0.94,
  "status": "analyzed"
}
```

---

### 4. Data Transformation

```http
POST /api/transform/structure
Content-Type: application/json
```

**Request**:
```json
{
  "document_id": "abc-123-def-456",
  "raw_data": {
    "SHIPPER NAME": {"value": "...", "confidence": 0.98},
    "RECEIVER NAME": {"value": "...", "confidence": 0.97}
  }
}
```

**Response**:
```json
{
  "document_id": "abc-123-def-456",
  "structured_data": {
    "shipper": "Global Electronics Ltd.",
    "receiver": "European Distribution Center",
    "goodsDescription": "Electronic Components",
    "value": "45850.00 USD",
    "countryOfOrigin": "United States",
    "hsCode": "8542.31",
    "weight": "125 KG"
  },
  "structure_confidence": 0.91,
  "status": "transformed"
}
```

---

### 5. Compliance Validation

```http
POST /api/compliance/validate
Content-Type: application/json
```

**Request**:
```json
{
  "document_id": "abc-123-def-456",
  "structured_data": {
    "shipper": "Global Electronics Ltd.",
    "receiver": "European Distribution Center",
    ...
  }
}
```

**Response**:
```json
{
  "document_id": "abc-123-def-456",
  "checks": [true, true, true, true, true],
  "compliance_confidence": 0.88,
  "issues": [],
  "reasoning": "All checks passed",
  "status": "validated"
}
```

**Checks performed**:
1. HS Code Validation
2. Country Restrictions
3. Value Declaration
4. Shipper Verification
5. Document Completeness

---

### 6. Customs Submission (Mock)

```http
POST /api/customs/submit
Content-Type: application/json
```

**Request**:
```json
{
  "document_id": "abc-123-def-456",
  "structured_data": {...}
}
```

**Response**:
```json
{
  "document_id": "abc-123-def-456",
  "submission_id": "CUSTOMS-20240115-A1B2C3D4",
  "status": "submitted",
  "timestamp": "2024-01-15T10:30:00Z",
  "message": "Document successfully submitted to customs authority (mock)"
}
```

---

## 🔧 Development

### Running in Development Mode

```bash
# With auto-reload enabled
python run.py
```

### Running Tests (if implemented)

```bash
pytest
```

### Code Style

The project follows PEP 8 style guidelines. Format code with:

```bash
black app/
```

---

## 🚢 Production Deployment

### Option 1: Azure App Service

1. **Create Azure App Service** (Python 3.11)
2. **Configure environment variables** in Azure Portal
3. **Deploy using Azure CLI**:
   ```bash
   az webapp up --name your-app-name --resource-group your-rg
   ```

### Option 2: Docker Container

Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "run:app"]
```

Build and run:
```bash
docker build -t customs-api .
docker run -p 5000:5000 --env-file .env customs-api
```

### Option 3: Heroku

```bash
# Install Heroku CLI and login
heroku login

# Create app
heroku create your-app-name

# Set environment variables
heroku config:set AZURE_STORAGE_CONNECTION_STRING=...
heroku config:set AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=...
heroku config:set AZURE_DOCUMENT_INTELLIGENCE_KEY=...
heroku config:set OPENAI_API_KEY=...

# Deploy
git push heroku main
```

### Production Checklist

- [ ] Set `FLASK_ENV=production`
- [ ] Set `FLASK_DEBUG=False`
- [ ] Use environment variables for all secrets
- [ ] Enable HTTPS only
- [ ] Configure CORS for specific origins only
- [ ] Set up monitoring and logging
- [ ] Implement rate limiting
- [ ] Use managed identity for Azure services
- [ ] Set up CI/CD pipeline

---

## 🔐 Security Best Practices

### Environment Variables

- ✅ **Never commit** `.env` files
- ✅ Use Azure Key Vault for production secrets
- ✅ Rotate API keys regularly
- ✅ Use managed identities when possible

### CORS Configuration

For production, update CORS in `app/__init__.py`:

```python
CORS(app, resources={
    r"/api/*": {
        "origins": ["https://your-frontend-domain.com"],
        "methods": ["GET", "POST"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})
```

### Authentication

For production, implement authentication:

```python
from functools import wraps
from flask import request

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != os.getenv('API_KEY'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function

@bp.route('/ocr/analyze', methods=['POST'])
@require_api_key
def analyze_document():
    # ...
```

---

## 🐛 Troubleshooting

### Azure Connection Issues

**Problem**: `Could not initialize Azure Blob Service`

**Solution**:
- Verify `AZURE_STORAGE_CONNECTION_STRING` is correct
- Check Azure Storage account is accessible
- Ensure container name exists

### Document Intelligence Errors

**Problem**: `Azure Document Intelligence not configured`

**Solution**:
- Verify endpoint URL is correct
- Check API key is valid
- Ensure Document Intelligence resource is deployed

### OpenAI API Errors

**Problem**: `OpenAI not configured`

**Solution**:
- Verify API key starts with `sk-`
- Check API key has sufficient credits
- Ensure correct model name (`gpt-4o` or `gpt-4o-mini`)

### CORS Errors

**Problem**: Frontend can't reach API

**Solution**:
- Check Flask CORS configuration
- Verify frontend is making requests to correct URL
- Check browser console for specific CORS errors

---

## 📊 Cost Estimation

### Azure Services

- **Blob Storage**: ~$0.018/GB/month (first 5GB free)
- **Document Intelligence**: Free tier = 500 pages/month, then $1.50/1000 pages
- **OpenAI API**: 
  - GPT-4o: ~$5-15 per 1M tokens input, ~$15-30 per 1M tokens output
  - GPT-4o-mini: ~$0.15-0.60 per 1M tokens

### Estimated Monthly Cost

For 1,000 documents/month:
- Storage: $0.05
- Document Intelligence: $3.00
- OpenAI (GPT-4o): $10-20
- **Total**: ~$13-23/month

---

## 🔍 Monitoring & Logging

### Application Logs

Logs are output to stdout. Configure logging:

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### Azure Application Insights

Add to `requirements.txt`:
```
opencensus-ext-azure
opencensus-ext-flask
```

Configure in `app/__init__.py`:
```python
from opencensus.ext.azure.log_exporter import AzureLogHandler
from opencensus.ext.flask.flask_middleware import FlaskMiddleware

logger = logging.getLogger(__name__)
logger.addHandler(AzureLogHandler(
    connection_string='InstrumentationKey=...'
))

middleware = FlaskMiddleware(app)
```

---

## 📚 Additional Resources

- [Azure Storage Python SDK](https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/storage/azure-storage-blob)
- [Azure AI Document Intelligence](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/)
- [OpenAI Python SDK](https://github.com/openai/openai-python)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)

---

## 🤝 Contributing

When contributing to the backend:

1. Follow PEP 8 style guidelines
2. Add docstrings to all functions
3. Update this README with any new endpoints
4. Test all changes locally before committing
5. Never commit secrets or API keys

---

## 📄 License

MIT License - See main project LICENSE file

---

**Built for the AI Document Processing Demo** 🚀
