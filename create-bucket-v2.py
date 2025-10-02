from minio import Minio
from minio.error import S3Error
import os

def get_minio_client(minio_endpoint, access_key, secret_key, secure=False):
    """
    Initializes and returns a MinIO client object.
    """
    try:
        client = Minio(
            endpoint=minio_endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        return client
    except Exception as e:
        print(f"Error initializing MinIO client: {e}")
        return None

def create_minio_bucket(client, bucket_name):
    """
    Creates a bucket if it doesn't already exist.
    Requires an initialized MinIO client.
    """
    if client is None:
        print("MinIO client is not initialized. Cannot create bucket.")
        return

    try:
        # Check if the bucket already exists
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
            print(f"Bucket '{bucket_name}' created successfully.")
        else:
            print(f"Bucket '{bucket_name}' already exists.")

    except S3Error as e:
        print(f"Error creating bucket '{bucket_name}': {e}")
    except Exception as e:
        print(f"An unexpected error occurred during bucket creation: {e}")

def list_minio_buckets(client):
    """
    Lists all buckets on the MinIO server.
    Requires an initialized MinIO client.
    """
    if client is None:
        print("MinIO client is not initialized. Cannot list buckets.")
        return

    try:
        buckets = client.list_buckets()
        if buckets:
            print("\n--- Listing MinIO Buckets ---")
            for bucket in buckets:
                print(f"  - {bucket.name} (Created: {bucket.creation_date})")
            print("-----------------------------\n")
        else:
            print("No buckets found on the MinIO server.")

    except S3Error as e:
        print(f"Error listing buckets: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during bucket listing: {e}")


if __name__ == "__main__":
    # MinIO server details
    # IMPORTANT: If your MinIO server is configured for HTTPS (secure=True),
    # ensure the endpoint does NOT include 'https://' or 'http://' prefix.
    # It should just be the hostname:port (e.g., "ip-172-31-36-232:9000").
    # If using self-signed certificates, you might need to handle certificate
    # validation on the client side or temporarily set secure=False for testing.
    minio_endpoint = "ip-172-31-0-171:9000"
    minio_access_key = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key = os.environ.get("MINIO_SECRET_KEY", "minioadmin")

    # Set 'secure=True' if your MinIO server is using HTTPS (recommended).
    # If you're running MinIO without TLS, set this to False.
    # Based on your `docker-compose.yml` modifications, it should be True now.
    is_secure_connection = False

    bucket_to_create = "teste-bucket-001"

    # 1. Get the MinIO client
    minio_client = get_minio_client(minio_endpoint, minio_access_key, minio_secret_key, is_secure_connection)

    if minio_client:
        # 2. Try to create the bucket
        create_minio_bucket(minio_client, bucket_to_create)

        # 3. List all buckets
        list_minio_buckets(minio_client)
    else:
        print("Failed to get MinIO client. Aborting operations.")
