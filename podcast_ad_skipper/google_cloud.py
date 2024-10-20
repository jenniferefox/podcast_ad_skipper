import json
import sys
from termcolor import colored
import requests
from pathlib import Path
from google.auth.exceptions import GoogleAuthError
from google.cloud import storage
from google.oauth2 import service_account
from google.cloud import bigquery

from podcast_ad_skipper.params import *


def auth_gc_storage():
    """Authenticates and returns a Google Cloud Storage client using service account credentials"""

    # Check if running in a Google Cloud environment (e.g., a VM or Cloud Function)
    try:
        # The metadata server is only available on Google Cloud environments
        response = requests.get("http://metadata.google.internal", timeout=1)
        if response.status_code == 200:
            # Running in Google Cloud, no need to specify credentials
            print("Running in Google Cloud environment.")
            print("Authenticated successfully! ✅")
            return storage.Client()

    except (requests.exceptions.RequestException, ValueError):
        # Running locally, load credentials from a file
        print("Running in local environment.")
        try:
            current_dir = Path(__file__).parent

            # Define the path to the service account folder (relative to the main project root)
            service_account_path = current_dir.parent / GOOGLE_CLOUD_SERVICE_ACCOUNT

            # Load and return the service account credentials
            credentials = service_account.Credentials.from_service_account_file(
                service_account_path
            )

            storage_client = storage.Client(project=GCP_PROJECT_ID, credentials=credentials)

            print("Authenticated successfully with GCS! ✅")
            return storage_client

        except FileNotFoundError:
            print("Error: The specified credentials file 'gcp/file_name.json' was not found.")
            print(colored("Failed to authenticate with Google Cloud Storage ❌", "red"))
            sys.exit(1)

        except GoogleAuthError as e:
            print(f"Error: Authentication failed with Google Cloud: {e}")
            print(colored("Failed to authenticate with Google Cloud Storage ❌", "red"))
            sys.exit(1)

        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            print(colored("Failed to authenticate with Google Cloud Storage ❌", "red"))
            sys.exit(1)


def upload_clips_gcs(client, bucket_name, filenames, blobname):
    """Upload every file in a list to a bucket, concurrently in a process pool.

    Each blob name is derived from the filename, not including the
    `source_directory` parameter.
    """
    if client is not None:
        bucket = client.bucket(bucket_name)
        d = bucket.blob(blobname)
        job = d.upload_from_file(filenames, content_type="audio/wav")
        result = job.result()

    if isinstance(result, Exception):
        print("Failed to upload {} due to exception: {}".format(blobname, result))
    else:
        print("Uploaded {} to {}.".format(blobname, bucket_name))


def retrieve_files_in_folder(storage_client,bucket_name, prefixes):
    '''Retrieving GCS files to use in VM preprocessing'''
    file_list = []
    bucket = storage_client.bucket(bucket_name)
    file_list_google_object = bucket.list_blobs(prefix=prefixes)
    for file in file_list_google_object:
        file_list.append(file)
    return file_list


def open_gcs_file(file):
    '''Open audio file from GCS'''
    audio_file = file.open('rb')
    return audio_file


def auth_gc_bigquery():
    """Authenticates and returns a Google Cloud BigQuery client using service account credentials"""
    try:
        with open('gcp/podcast-ad-skipper-0dd8dd2c5ac1.json') as source:
            info = json.load(source)

        bq_credentials = service_account.Credentials.from_service_account_info(info)

        bq_client = bigquery.Client(project=GCP_PROJECT_ID, credentials=bq_credentials)
        print("Authenticated successfully with BigQuery! ✅")

        return bq_client

    except FileNotFoundError:
        print("Error: The specified credentials file 'gcp/file_name.json' was not found.")
        print("Failed to authenticate with Google Cloud Storage ❌", "red")
        sys.exit(1)

    except GoogleAuthError as e:
        print(f"Error: Authentication failed with Google Cloud: {e}")
        print("Failed to authenticate with Google Cloud Storage ❌", "red")
        sys.exit(1)

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        print("Failed to authenticate with Google Cloud Storage ❌", "red")
        sys.exit(1)



def append_arrays_to_bq(data, bq_client, table_id):
    '''Uploading data (as dataframes) to BQ'''
    bq_client = auth_gc_bigquery()
    # Create df out of the np arrays, to upload to bq
    # Use WRITE_APPEND to add to the existing table
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_APPEND",
        schema=[
            bigquery.SchemaField("spectrogram", "FLOAT", mode="REPEATED"),
            bigquery.SchemaField("labels", "STRING"),
            bigquery.SchemaField("seconds", "INTEGER"),
            bigquery.SchemaField("durations", "INTEGER"),
            bigquery.SchemaField("podcast_names", "STRING")
        ]
    )
    job = bq_client.load_table_from_dataframe(data, table_id, job_config=job_config)
    print(job.result())
    print(f"Appended rows to {table_id}")


if __name__ == '__main__':
    auth_gc_storage()
    auth_gc_bigquery()
