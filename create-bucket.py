from minio import Minio
from minio.error import S3Error
import os

def create_minio_bucket(bucket_name, minio_endpoint, access_key, secret_key, secure=True):
    try:
        # Create a client for your MinIO server
        client = Minio(
            endpoint=minio_endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure, # Set to False if your MinIO is not using HTTPS
        )

        # Check if the bucket already exists
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
            print(f"Bucket '{bucket_name}' created successfully.")
        else:
            print(f"Bucket '{bucket_name}' already exists.")

    except S3Error as e:
        print(f"Error creating bucket: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    # Replace with your MinIO server details
    minio_endpoint = "ip-172-31-36-232:9000" # Do not include https:// if secure=True
    minio_access_key = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
    bucket_to_create = "teste-bucket-001"

    create_minio_bucket(bucket_to_create, minio_endpoint, minio_access_key, minio_secret_key, secure=False)
