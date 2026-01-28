"""
Flask Application Entry Point
Runs the AI Document Processing API server
"""
# ============================================================
# TRACING SETUP - MUST BE FIRST (before any agent_framework imports)
# ============================================================
# This configures OpenTelemetry to export traces to AI Toolkit
# The SDK automatically instruments all agent_framework operations
from agent_framework.observability import configure_otel_providers

configure_otel_providers(
    vs_code_extension_port=4317,  # AI Toolkit gRPC port
    enable_sensitive_data=True    # Capture prompts and completions
)
print("✓ OpenTelemetry tracing configured (AI Toolkit port 4317)")
# ============================================================

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
