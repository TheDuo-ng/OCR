import os
import sys
import io
import threading
import concurrent.futures
import tkinter as tk
from tkinter import messagebox
import argparse
import time

# Import Google API libraries
import httplib2
from apiclient import discovery, errors
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage
from apiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

# --- CONFIGURATION ---
SCOPES = "https://www.googleapis.com/auth/drive"
CLIENT_SECRET_FILE = "credentials.json"
APPLICATION_NAME = "Python OCR Processor"
MAX_WORKERS = 10
MAX_RETRIES = 3 # Number of retries for API calls

def get_credentials(args):
    """Gets valid user credentials from storage."""
    credential_path = 'token.json'
    store = Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        if not os.path.exists(CLIENT_SECRET_FILE):
            print(f"[ERROR] Cannot find '{CLIENT_SECRET_FILE}'.")
            return None
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = APPLICATION_NAME
        credentials = tools.run_flow(flow, store, args)
    return credentials

def ocr_image_with_google_drive(image_path, credentials):
    """
    Performs OCR on an image file using the Google Drive API with a retry mechanism.
    """
    thread_name = threading.current_thread().name
    retries = 0
    while retries < MAX_RETRIES:
        try:
            http = credentials.authorize(httplib2.Http())
            service = discovery.build("drive", "v3", http=http)

            file_metadata = {
                'name': os.path.basename(image_path),
                'mimeType': 'application/vnd.google-apps.document'
            }
            
            with open(image_path, 'rb') as fh:
                media = MediaIoBaseUpload(fh, mimetype='image/png', resumable=True)
                res = service.files().create(body=file_metadata, media_body=media, fields='id').execute()

            file_id = res.get('id')
            if not file_id:
                print(f"[WARNING][{thread_name}] Google Drive did not return a file ID for {os.path.basename(image_path)}.")
                return ""

            request = service.files().export_media(fileId=file_id, mimeType="text/plain")
            fh_download = io.BytesIO()
            downloader = MediaIoBaseDownload(fh_download, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()

            service.files().delete(fileId=file_id).execute()

            text_content = fh_download.getvalue().decode('utf-8')
            
            # --- POST-PROCESSING FIX ---
            # Clean up the OCR result by removing leading underscores and spaces
            cleaned_text = " ".join(filter(None, text_content.splitlines()))
            final_text = cleaned_text.lstrip('_ ').strip()
            return final_text
            # --- END FIX ---

        except errors.HttpError as e:
            if e.resp.status in [403, 500, 503]:
                retries += 1
                wait_time = (2 ** retries)
                print(f"[WARNING][{thread_name}] API error for {os.path.basename(image_path)} (Status: {e.resp.status}). Retrying in {wait_time}s... ({retries}/{MAX_RETRIES})")
                time.sleep(wait_time)
            else:
                print(f"[ERROR][{thread_name}] Unrecoverable API error for {os.path.basename(image_path)}: {e}")
                return ""
        except Exception as e:
            print(f"[ERROR][{thread_name}] General error during OCR for image {os.path.basename(image_path)}: {e}")
            return ""

    print(f"[ERROR][{thread_name}] Failed to process image {os.path.basename(image_path)} after {MAX_RETRIES} retries.")
    return ""


def main(args):
    image_folder = args.image_folder
    srt_path = args.srt_path
    
    print("================ STARTING OCR PROCESSING ================")
    
    # --- Authentication ---
    print("[INFO] Authenticating with Google Drive...")
    credentials = get_credentials(args)
    if not credentials:
        print("[ERROR] Authentication failed. Exiting.")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Authentication Error", f"Could not get Google credentials. Make sure '{CLIENT_SECRET_FILE}' exists and is valid.")
        return
    print("[INFO] Authentication successful.")

    # --- Get image list ---
    image_files = [os.path.join(image_folder, f) for f in os.listdir(image_folder) if f.endswith('.png')]
    if not image_files:
        print("[WARNING] No image files found in the directory.")
        return
    print(f"[INFO] Found {len(image_files)} images to process.")

    # --- Multi-threaded processing ---
    srt_blocks = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_image = {executor.submit(ocr_image_with_google_drive, img_path, credentials): img_path for img_path in image_files}

        processed_count = 0
        for future in concurrent.futures.as_completed(future_to_image):
            processed_count += 1
            img_path = future_to_image[future]
            img_name = os.path.basename(img_path)
            try:
                ocr_text = future.result()
                if ocr_text:
                    time_parts = os.path.splitext(img_name)[0].split('__')
                    start_part = time_parts[0]
                    start_hms = '_'.join(start_part.split('_')[:-1])
                    start_ms = start_part.split('_')[-1]
                    start_time_srt = f"{start_hms.replace('_', ':')},{start_ms}"

                    end_part = time_parts[1]
                    end_hms = '_'.join(end_part.split('_')[:-1])
                    end_ms = end_part.split('_')[-1]
                    end_time_srt = f"{end_hms.replace('_', ':')},{end_ms}"
                    
                    srt_blocks[start_time_srt] = f"{start_time_srt} --> {end_time_srt}\n{ocr_text}\n"
                    print(f"[PROGRESS] {processed_count}/{len(image_files)} | OCR successful: {img_name}")
                else:
                    print(f"[PROGRESS] {processed_count}/{len(image_files)} | OCR no result: {img_name}")
            except Exception as exc:
                print(f'[ERROR] Image {img_name} generated an exception: {exc}')

    # --- Write SRT file ---
    if srt_blocks:
        print(f"[INFO] Preparing to write {len(srt_blocks)} subtitle blocks to {srt_path}...")
        with open(srt_path, 'w', encoding='utf-8') as f:
            sorted_times = sorted(srt_blocks.keys())
            for i, time_key in enumerate(sorted_times):
                f.write(f"{i + 1}\n")
                f.write(srt_blocks[time_key] + "\n")
        print(f"[SUCCESS] Successfully created SRT file: {srt_path}")
    else:
        print("[WARNING] No subtitles were recognized.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process subtitle images using Google Drive OCR.",
                                     parents=[tools.argparser])
    parser.add_argument('--image_folder', required=True, help='Directory containing subtitle images.')
    parser.add_argument('--srt_path', required=True, help='Path to save the final .srt file.')
    
    args = parser.parse_args()
    
    main(args)
