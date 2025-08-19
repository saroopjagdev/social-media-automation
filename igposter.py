import sqlite3
import random
import requests
import os
import shutil
import webbrowser
import pyperclip
import time
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# NEW imports for S3
import boto3
from botocore.exceptions import ClientError

# Google Drive API scopes and credentials
SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDENTIALS_FILE = 'C:/Users/ssjag/OneDrive/Programming/ig automation/client_secret.json'

# Instagram & Facebook App Credentials (keep tokens secure)
FB_APP_ID = '1282234560118772'
FB_APP_SECRET = 'c0a21df1d30567649df3ebbe4a6b1acf'
fb_access_token = "REPLACE_WITH_YOUR_PAGE_TOKEN"

IG_APP_ID = '8143980319030013'
IG_APP_SECRET = 'f2c6f70653cf0d1601dd3d3a78a1ad18'
ig_access_token = 'REPLACE_WITH_VALID_IG_ACCESS_TOKEN'  # must have instagram_content_publish

# Instagram User IDs
golf_ig_user_id = '17841458227887736'
food_ig_user_id = '17841473324787008'
fashion_ig_user_id = '17841460751104001'

food_fb_user_id = '616379148221623'

# ---------- DB & downloader functions (unchanged) ----------
def get_random_video_from_db(db_name):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("SELECT link, creator FROM videos WHERE posted != 'yes'")
    videos = cursor.fetchall()
    
    if not videos:
        conn.close()
        return None, None
    
    random_video = random.choice(videos)
    link, creator = random_video
    cursor.execute("UPDATE videos SET posted = 'yes' WHERE link = ?", (link,))
    conn.commit()
    conn.close()
    
    return link, creator

def download(tiktok_link, creator):
    print(f"Downloading TikTok video from: {tiktok_link}")

    # 1. Call Tikwm API
    api_url = "https://tikwm.com/api/"
    params = {"url": tiktok_link}
    response = requests.get(api_url, params=params)

    if response.status_code != 200 or 'data' not in response.json():
        raise Exception("Failed to get video info from Tikwm.")

    video_data = response.json()['data']
    download_url = video_data.get('play')

    if not download_url:
        raise Exception("No video URL found in Tikwm response.")

    # 2. Download the video
    video_content = requests.get(download_url).content

    # 3. Construct filename
    parts = tiktok_link.strip('/').split('/')
    username = creator.replace('@', '').replace(' ', '_')
    video_id = parts[-1]
    new_filename = f"{username}_{video_id}.mp4"

    target_dir = r"C:/Users/ssjag/OneDrive/Programming/ig automation/downloaded_videos"
    os.makedirs(target_dir, exist_ok=True)
    new_filepath = os.path.join(target_dir, new_filename)

    # 4. Save video
    with open(new_filepath, 'wb') as f:
        f.write(video_content)

    print(f"Video downloaded and saved to: {new_filepath}")
    return new_filepath



# ---------- NEW: S3 upload & presigned URL ----------
def upload_to_s3_presigned(file_path, bucket_name="saroop-ig-uploads", object_name=None, expire_seconds=604800):
    """
    Uploads local file to S3 and returns a presigned GET URL valid for expire_seconds (default 7 days).
    Requires AWS credentials in env or ~/.aws/credentials.
    """

    if object_name is None:
        object_name = os.path.basename(file_path)

    s3_client = boto3.client('s3')
    try:
        print(f"Uploading {file_path} to S3 bucket {bucket_name} as {object_name}...")
        s3_client.upload_file(
            Filename=file_path,
            Bucket=bucket_name,
            Key=object_name,
            ExtraArgs={'ContentType': 'video/mp4'}
        )
    except ClientError as e:
        raise Exception(f"S3 upload failed: {e}")

    try:
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': object_name},
            ExpiresIn=expire_seconds
        )
        print(f"Generated presigned S3 URL (expires in {expire_seconds}s): {presigned_url}")
        return presigned_url
    except ClientError as e:
        raise Exception(f"Failed to generate presigned URL: {e}")

# ---------- Updated post_to_instagram uses S3 presigned URL ----------
def post_to_instagram(video_path, caption, ig_user_id):
    """
    Accepts a local file path; uploads it to S3 with a presigned URL, then
    creates an IG media container and publishes it.
    """
    # Upload to S3 and get a direct presigned URL
    try:
        # uses S3_BUCKET_NAME env var if set
        video_url = upload_to_s3_presigned(video_path)
    except Exception as e:
        print("Failed to upload to S3:", e)
        return None

    url = f'https://graph.facebook.com/v17.0/{ig_user_id}/media'
    payload = {
        'media_type': 'REELS',
        'video_url': video_url,
        'caption': caption,
        'access_token': ig_access_token
    }
    response = requests.post(url, data=payload)
    if response.status_code != 200:
        print(f'Error creating media container: {response.json()}')
        return None

    container_id = response.json().get('id')
    print(f'Created media container with ID: {container_id}')

    max_retries = 30
    sleep_time = 10

    for attempt in range(max_retries):
        publish_url = f'https://graph.facebook.com/v17.0/{ig_user_id}/media_publish'
        publish_payload = {'creation_id': container_id, 'access_token': ig_access_token}
        publish_response = requests.post(publish_url, data=publish_payload)
        
        if publish_response.status_code == 200:
            media_id = publish_response.json().get('id')
            print(f'Published media with ID: {media_id}')
            return media_id
        else:
            error_data = publish_response.json()
            if error_data.get('error', {}).get('code') == 9007:
                print(f"Attempt {attempt + 1}: Media not ready. Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)
            else:
                print(f"Error publishing media container: {publish_response.json()}")
                return None

    print("Failed to publish media after multiple attempts.")
    return None

# ---------- Facebook upload unchanged ----------
def post_to_facebook_page(video_path, caption, fb_page_id):
    url = f'https://graph.facebook.com/v17.0/{fb_page_id}/videos'
    files = {'source': open(video_path, 'rb')}
    payload = {
        'description': caption,
        'access_token': fb_access_token,
        'published': 'true'
    }
    response = requests.post(url, files=files, data=payload)
    if response.status_code != 200:
        print(f'Error uploading video: {response.json()}')
        return None
    video_id = response.json().get('id')
    print(f'Video uploaded successfully. Video ID: {video_id}')
    return video_id

# -------------------------
# Main flow (unchanged logic, uses local path for IG and FB)
# -------------------------
tiktok_link, creator = get_random_video_from_db('foodvids.db')
if tiktok_link:
    video_path = download(tiktok_link, creator)
    s3_url = upload_to_s3_presigned(video_path)

    caption = f"Follow for the best low calorie recipes to get your dream body this summer!\nvia @{creator}\n#lowcalorie #mealprep #cooking #weightloss #loseweight"
    # Post to Instagram using S3 presigned URL under the hood
    post_to_instagram(video_path, caption, food_ig_user_id)
    # Post to Facebook from local file
    post_to_facebook_page(video_path, caption, food_fb_user_id)
else:
    print("No unposted food videos found.")

tiktok_link, creator = get_random_video_from_db('mensfashionvids.db')
if tiktok_link:
    video_path = download(tiktok_link, creator)
    s3_url = upload_to_s3_presigned(video_path)
    caption = f"Follow for more men's fashion inspiration!\nvia @{creator}\n#oldmoney #starboy #summerstyle #grisch #mensfashion"
    post_to_instagram(video_path, caption, fashion_ig_user_id)
else:
    print("No unposted fashion videos found.")
