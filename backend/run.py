"""
Flask Application Entry Point
Runs the AI Document Processing API server
"""
import os
import sys

# Force unbuffered output for Azure App Service
sys.stdout = sys.stderr  # Redirect stdout to stderr (captured by gunicorn)
os.environ['PYTHONUNBUFFERED'] = '1'

# ============================================================
# TRACING SETUP - Only enable if agent_framework is installed
# ============================================================
# This configures OpenTelemetry to export traces to AI Toolkit
# The SDK automatically instruments all agent_framework operations
try:
    from agent_framework.observability import configure_otel_providers
    configure_otel_providers(
        vs_code_extension_port=4317,  # AI Toolkit gRPC port
        enable_sensitive_data=True    # Capture prompts and completions
    )
    print("✓ OpenTelemetry tracing configured (AI Toolkit port 4317)", flush=True)
except ImportError:
    # agent_framework not installed - skip tracing setup
    # This is normal in production deployments
    pass
# ============================================================

from app import create_app

app = create_app()

if __name__ == '__main__':
    debug_enabled = os.getenv('FLASK_DEBUG', '').lower() in {'1', 'true', 'yes'}
    app.run(debug=debug_enabled, host='0.0.0.0', port=5000, use_reloader=False)
