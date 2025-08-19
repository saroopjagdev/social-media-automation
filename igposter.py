import sqlite3
import random
import requests
import os
import time
import boto3
from botocore.exceptions import ClientError
from info import FB_APP_ID, FB_APP_SECRET, IG_APP_ID, IG_APP_SECRET, ig_access_token, PAGES



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



def upload_to_s3_presigned(file_path, bucket_name="saroop-ig-uploads", object_name=None, expire_seconds=604800):


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


def post_to_instagram(video_path, caption, ig_user_id, ig_access_token):
    video_url = upload_to_s3_presigned(video_path)
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

    # Poll until published
    for _ in range(30):
        publish_url = f'https://graph.facebook.com/v17.0/{ig_user_id}/media_publish'
        publish_payload = {'creation_id': container_id, 'access_token': ig_access_token}
        publish_response = requests.post(publish_url, data=publish_payload)
        if publish_response.status_code == 200:
            media_id = publish_response.json().get('id')
            print(f'Published media with ID: {media_id}')
            return media_id
        elif publish_response.json().get('error', {}).get('code') == 9007:
            print("Media not ready. Retrying...")
            time.sleep(10)
        else:
            print(f"Error publishing: {publish_response.json()}")
            return None
    return None


def post_to_facebook_page(video_path, caption, fb_page_id, fb_access_token):
    if not fb_page_id or not fb_access_token:
        print("Skipping Facebook upload (no fb_page_id or token configured).")
        return None
    url = f'https://graph.facebook.com/v17.0/{fb_page_id}/videos'
    with open(video_path, 'rb') as f:
        files = {'source': f}
        payload = {
            'description': caption,
            'access_token': fb_access_token,
            'published': 'true'
        }
        response = requests.post(url, files=files, data=payload)
    if response.status_code != 200:
        print(f'Error uploading to Facebook: {response.json()}')
        return None
    print(f'FB video uploaded: {response.json()}')
    return response.json().get('id')



for page_name, page_info in PAGES.items():
    print(f"\n--- Processing page: {page_name} ---")
    tiktok_link, creator = get_random_video_from_db(page_info["db"])
    if not tiktok_link:
        print(f"No unposted videos found for {page_name}.")
        continue

    video_path = download(tiktok_link, creator)
    caption = f"{page_info['default_caption']}\nvia @{creator}"

    # Instagram
    post_to_instagram(video_path, caption, page_info["ig_user_id"], ig_access_token)

    post_to_facebook_page(video_path, caption, page_info["fb_page_id"], page_info["fb_access_token"])