# Fresh-clone work-laptop bootstrap

Run these commands on the real work/robot laptop, not the simulation laptop.
Choose any parent folder; no command assumes a fixed checkout path.

## 1. Clone and create the environment

```powershell
git clone https://github.com/YOUR-ORG/synthesis_planner.git
Set-Location .\synthesis_planner

conda create -n llm python=3.11 -y
conda activate llm
conda install -y -c conda-forge rdkit
python -m pip install -r requirements.txt
```

If an approved `llm` environment already exists, activate it instead of
creating a new one.

## 2. Configure the checkout for Vertex AI

```powershell
Copy-Item .env.vertexai.example .env
notepad .env
```

Replace `your-gcp-project-id` with the assigned project ID. Keep
`GOOGLE_CLOUD_LOCATION=us-central1` unless your project uses another supported
Vertex location. Do not add an API key.

## 3. Configure gcloud and ADC

```powershell
gcloud auth login
gcloud config set project YOUR_GCP_PROJECT_ID
gcloud services enable aiplatform.googleapis.com
gcloud auth application-default login
```

Billing must be enabled for the project and the logged-in identity normally
needs `roles/aiplatform.user` (or an equivalent approved role).

## 4. Verify before making a real request

```powershell
python scripts\validate_gcloud_setup.py
python scripts\validate_gcloud_setup.py --check-adc
```

The first command is an offline doctor report. The second may refresh ADC but
does not call Vertex AI. Read its `next_command` value if anything is missing.

## 5. Explicitly verify Vertex and the agent path

These two commands make real, tiny external Vertex AI requests. They do not
control laboratory hardware:

```powershell
python scripts\validate_gcloud_setup.py --check-adc --smoke-test
python scripts\run_agent_smoke.py --smoke-test
```

Only after these pass should a separate, explicitly approved robot workflow be
considered. This repository's smoke commands are hardware-free by design.
