"""Publica out/video.mp4 no YouTube e só depois regista o vídeo no histórico."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from history import record_publish
from validation import assert_ready_for_upload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
RETRIABLE = {500, 502, 503, 504}


def main() -> None:
    assert_ready_for_upload()

    meta = json.loads(Path("out/meta.json").read_text(encoding="utf-8"))
    secret = json.loads(Path("client_secret.json").read_text(encoding="utf-8"))["installed"]
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri=secret["token_uri"],
        client_id=secret["client_id"],
        client_secret=secret["client_secret"],
        scopes=SCOPES,
    )
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    body = {
        "snippet": {
            "title": meta["title"][:100],
            "description": meta["description"][:4900],
            "tags": meta.get("tags", [])[:15],
            "categoryId": "27",  # Education
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": os.getenv("YT_PRIVACY", "public"),
            "selfDeclaredMadeForKids": False,
        },
    }
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload("out/video.mp4", mimetype="video/mp4", resumable=True, chunksize=-1),
    )

    response = None
    for attempt in range(1, 6):
        try:
            while response is None:
                _, response = request.next_chunk()
            break
        except HttpError as exc:
            if exc.resp.status not in RETRIABLE or attempt == 5:
                raise
            print(f"Erro {exc.resp.status} no upload, nova tentativa ({attempt})")
            time.sleep(5 * attempt)

    video_id = response["id"]
    record_publish(meta, video_id)
    Path("out/upload_result.json").write_text(json.dumps({"video_id": video_id}), encoding="utf-8")
    print(f"Uploaded: {video_id} -> https://youtube.com/shorts/{video_id}")


if __name__ == "__main__":
    main()
