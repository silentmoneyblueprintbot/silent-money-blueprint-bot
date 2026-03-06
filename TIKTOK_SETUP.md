# TikTok Publishing Setup

This project now supports optional TikTok publishing using TikTok's official Content Posting API.

## Required credentials

Add this repository secret:

- `TIKTOK_ACCESS_TOKEN`

Optional repository variable:

- `TIKTOK_PRIVACY_LEVEL` (`SELF_ONLY`, `MUTUAL_FOLLOW_FRIENDS`, or `PUBLIC_TO_EVERYONE`)

## Required scopes and products (TikTok app)

Your TikTok app/user token must have Content Posting permissions, including:

- `video.publish`
- `video.upload`

The token must belong to the same TikTok creator account where you want to publish.

## Workflow behavior

- If `TIKTOK_ACCESS_TOKEN` is missing, TikTok upload step is skipped.
- If token exists, workflow calls:
  1. `creator_info/query`
  2. `video/init`
  3. binary upload to `upload_url`
  4. `status/fetch`

## Common errors

- `unauthorized_client` or permission errors:
  - token is from wrong app/user
  - missing scope or app access not approved
- duration/feature errors:
  - video exceeds creator limits returned by TikTok API

## Notes

- Keep YouTube credentials as-is; TikTok upload is additive and optional.
- For stable production publishing, use long-lived tokens and documented token refresh flow from TikTok app configuration.
