"""
One-time script: setup GCS folder for ig_posts image storage in existing bucket.
Run locally: python scripts/setup_gcs_bucket.py [--bucket BUCKET_NAME] [--folder FOLDER]

What it does:
1. Lists all buckets in the project
2. Uses existing bucket (no creation)
3. Tests upload to folder prefix
4. Prints env vars to copy into .env.production

Requires: GCS_SERVICE_ACCOUNT_JSON env var (single-line JSON of service account key)
"""
import argparse
import json
import os
import sys

_sa_json_str = os.environ.get("GCS_SERVICE_ACCOUNT_JSON", "")
if not _sa_json_str:
    print("Error: set GCS_SERVICE_ACCOUNT_JSON env var (single-line service account JSON)")
    sys.exit(1)
SA_JSON = json.loads(_sa_json_str)

PROJECT_ID = SA_JSON.get("project_id", "")

try:
    from google.cloud import storage
    from google.oauth2 import service_account
except ImportError:
    print("Installing google-cloud-storage...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "google-cloud-storage", "-q"])
    from google.cloud import storage
    from google.oauth2 import service_account


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", default="", help="Bucket name (leave empty to list all)")
    parser.add_argument("--folder", default="getcontact-ig", help="Folder prefix inside bucket")
    args = parser.parse_args()

    credentials = service_account.Credentials.from_service_account_info(SA_JSON)
    client = storage.Client(project=PROJECT_ID, credentials=credentials)

    if not args.bucket:
        print("Listing buckets...")
        try:
            buckets = list(client.list_buckets())
            if buckets:
                print("Buckets found:")
                for b in buckets:
                    print(f"  - {b.name}")
            else:
                print("No buckets found in project.")
        except Exception as e:
            print(f"Cannot list buckets: {e}")
        print("\nRun again with: --bucket BUCKET_NAME --folder getcontact-ig")
        sys.exit(0)

    bucket_name = args.bucket
    folder = args.folder.strip("/")

    # 1. Create bucket if not exists
    try:
        bucket = client.create_bucket(bucket_name, location="ASIA-SOUTHEAST2")
        print(f"✓ Bucket '{bucket_name}' created (jakarta region)")
    except Exception as e:
        if "409" in str(e) or "already" in str(e).lower():
            bucket = client.bucket(bucket_name)
            print(f"✓ Bucket '{bucket_name}' already exists")
        else:
            print(f"✗ Failed to create bucket: {e}")
            sys.exit(1)

    # 2. Set public read
    try:
        policy = bucket.get_iam_policy(requested_policy_version=3)
        policy.bindings.append({"role": "roles/storage.objectViewer", "members": {"allUsers"}})
        bucket.set_iam_policy(policy)
        print("✓ Public read enabled")
    except Exception as e:
        print(f"  (skipping public access: {e})")

    # 3. Test upload ke folder
    test_key = f"{folder}/_test/ping.txt"
    try:
        blob = bucket.blob(test_key)
        blob.upload_from_string(b"ok", content_type="text/plain")
        test_url = f"https://storage.googleapis.com/{bucket_name}/{test_key}"
        blob.delete()
        print(f"\n✓ Upload test OK — folder '{folder}/' accessible")
    except Exception as e:
        print(f"\n✗ Upload failed: {e}")
        print("  → Pastikan service account punya role Storage Object Admin di bucket ini")
        sys.exit(1)

    # 4. Print env vars
    sa_json_oneline = json.dumps(SA_JSON, separators=(',', ':'))
    public_url = f"https://storage.googleapis.com/{bucket_name}/{folder}"
    print("\n" + "="*60)
    print("Copy ke .env.production (GitLab ENV_PRODUCTION variable):")
    print("="*60)
    print(f"BUCKET_PROVIDER=gcs")
    print(f"GCS_SERVICE_ACCOUNT_JSON={sa_json_oneline}")
    print(f"BUCKET_NAME={bucket_name}")
    print(f"BUCKET_FOLDER={folder}")
    print(f"BUCKET_PUBLIC_URL={public_url}")
    print("="*60)


if __name__ == "__main__":
    main()
