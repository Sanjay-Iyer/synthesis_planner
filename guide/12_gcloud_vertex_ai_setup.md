# LLM provider modes and safe validation

`LLM_PROVIDER` is the only selector for the repository's LLM behavior. The
same clone can live at any path; `.env` is always loaded from that checkout,
not from the current terminal directory.

| Provider | Intended laptop | Credentials | External call behavior |
|---|---|---|---|
| `mock` | Personal simulation laptop and CI | None | Never makes a network request |
| `api-key` | Personal development laptop only | Local `GEMINI_API_KEY` or `GOOGLE_API_KEY` | Only with an explicit smoke-test command |
| `vertexai` | Work/robot laptop | gcloud Application Default Credentials | Only with an explicit smoke-test command |

An unset `LLM_PROVIDER` means `mock`; this is the safe fresh-clone default.
There is no automatic inference from an API key or legacy environment flag.

## Personal simulation laptop

Normal offline checks stay in the `ai` environment and do not need gcloud,
Google credentials, an API key, or laboratory hardware:

```powershell
conda run -n ai python -m pytest
conda run -n ai python scripts\validate_gcloud_setup.py
conda run -n ai python scripts\run_agent_smoke.py --mock
```

The doctor command reports `provider: mock`, `adc_status: not-required`, and a
next command. It does not make a Vertex request unless `--smoke-test` is added.

## Personal API-key mode (optional)

Only on a personal laptop, copy `.env.api-key.example` to `.env` and put the
key in that local ignored file. Never copy this `.env` to the work/robot
laptop. API-key requests are still opt-in:

```powershell
conda run -n ai python scripts\run_agent_smoke.py --smoke-test
```

## Work/robot laptop Vertex AI mode

Copy `.env.vertexai.example` to `.env` and set:

```dotenv
LLM_PROVIDER=vertexai
GOOGLE_CLOUD_PROJECT=YOUR_GCP_PROJECT_ID
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_VERTEX_API_TRANSPORT=rest
GEMINI_MODEL=gemini-2.5-flash
```

Do not set `GEMINI_API_KEY` or `GOOGLE_API_KEY` on that laptop. In Vertex mode
the code does not read either variable and constructs `google-genai` with
`vertexai=True`, project, and location only. The SDK obtains short-lived
credentials through gcloud ADC.

`GOOGLE_VERTEX_API_TRANSPORT=rest` is mandatory. This repository uses the
REST-based `google-genai` client rather than Windows gRPC transport.

Run the non-LLM ADC check before any real smoke test:

```powershell
python scripts\validate_gcloud_setup.py --check-adc
```

Then, only when a real external request is intended:

```powershell
python scripts\validate_gcloud_setup.py --check-adc --smoke-test
python scripts\run_agent_smoke.py --smoke-test
```

The smoke commands make small external requests but never touch lab hardware.
They validate ADC, project IAM, API enablement, network access, model access,
and structured LLM response handling together.

## Failure behavior

An explicit but incomplete `LLM_PROVIDER=vertexai` configuration fails clearly:
it does not switch to API-key mode or mock mode. Common fixes appear in the
doctor command's `next_command` field. The real work/robot laptop uses
`conda activate llm`; this simulation laptop remains `ai` only.
