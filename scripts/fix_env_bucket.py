"""Fix .env.production — remove broken bucket section and re-append correctly."""
import json, os, re

ENV_PATH = "C:/Users/narad/Programming/GetContactAI/.env.production"

_sa_json_str = os.environ.get("GCS_SERVICE_ACCOUNT_JSON", "")
if not _sa_json_str:
    raise RuntimeError(
        "Set GCS_SERVICE_ACCOUNT_JSON env var before running this script.\n"
        "Export the service account JSON as a single-line string."
    )
SA_JSON = json.loads(_sa_json_str)

# Read existing, strip any previous bucket section
with open(ENV_PATH, "r", encoding="utf-8") as f:
    content = f.read()

content = re.sub(r'\n# --- Object Storage.*', '', content, flags=re.DOTALL).rstrip()

# Append bucket section with properly escaped JSON (single line)
sa_json_str = json.dumps(SA_JSON, separators=(',', ':'))
bucket_section = f"""

# --- Object Storage (GCS) ---
BUCKET_PROVIDER=gcs
GCS_SERVICE_ACCOUNT_JSON={sa_json_str}
BUCKET_NAME=getcontact-images
BUCKET_FOLDER=getcontact-ig
BUCKET_PUBLIC_URL=https://storage.googleapis.com/getcontact-images/getcontact-ig
"""

with open(ENV_PATH, "w", encoding="utf-8") as f:
    f.write(content + bucket_section)

print("Done. Last 6 lines:")
lines = (content + bucket_section).strip().splitlines()
for l in lines[-6:]:
    print(f"  {l[:80]}{'...' if len(l)>80 else ''}")
