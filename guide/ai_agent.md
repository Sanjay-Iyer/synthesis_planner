
# LLM auth by laptop role:
# Simulation laptop testing may use LLM_PROVIDER=api-key + GOOGLE_API_KEY.
# Real robot laptop live interactions must use Vertex AI / gcloud ADC.
LLM_PROVIDER=vertexai
GOOGLE_API_KEY=                         # Simulation laptop testing only
GOOGLE_CLOUD_PROJECT=your-project-id    # Required for Vertex AI / gcloud ADC
GOOGLE_CLOUD_LOCATION=us-central1
GEMINI_MODEL=gemini-2.5-flash           # Or any supported Gemini model

# Optional
GEMINI_BASE_URL=                # Leave blank unless using a proxy
REMOTE_USER_STORAGE=/var/lib/jupyter/notebooks   # Robot filesystem path