from __future__ import annotations

import json
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from validation import assert_ready_for_upload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")


def main() -> None:
    assert_ready_for_upload()

    refresh_token = os.environ["YOUTUBE_REFRESH_TOKEN"]
    data = json.loads(Path("client_secret.json").read_text(encoding="utf-8"))
    installed = data["installed"]

    title_path = Path("meta_title.txt")
    desc_path = Path("meta_desc.txt")
    video_path = Path("out/video.mp4")

    require_file(title_path)
    require_file(desc_path)
    require_file(video_path)

    title = title_path.read_text(encoding="utf-8").strip()
    description = desc_path.read_text(encoding="utf-8").strip()

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
                "title": title,
                "description": description,
                "categoryId": "22",
            },
            "status": {"privacyStatus": "public"},
        },
        media_body=MediaFileUpload(str(video_path)),
    )

    response = request.execute()
    print("Uploaded:", response["id"])


if __name__ == "__main__":
    main()
