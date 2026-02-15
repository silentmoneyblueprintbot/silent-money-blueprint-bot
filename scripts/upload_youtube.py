import json
import os
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def main():
    refresh_token = os.environ["YOUTUBE_REFRESH_TOKEN"]
    data = json.loads(Path("client_secret.json").read_text())
    installed = data["installed"]

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=installed["token_uri"],
        client_id=installed["client_id"],
        client_secret=installed["client_secret"],
        scopes=SCOPES,
    )

    youtube = build("youtube", "v3", credentials=creds)

    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": Path("meta_title.txt").read_text(),
                "description": Path("meta_desc.txt").read_text(),
                "categoryId": "22"
            },
            "status": {"privacyStatus": "public"}
        },
        media_body=MediaFileUpload("out/video.mp4")
    )

    response = request.execute()
    print("Uploaded:", response["id"])

if __name__ == "__main__":
    main()
