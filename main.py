#!/usr/bin/env python3
import sys
import argparse
from tikcli.client import TikTokClient
from tikcli.ui import TerminalUI
from tikcli.media import play_video_in_terminal
from tikcli.config import SESSION_FILE


def main():
    parser = argparse.ArgumentParser(
        description="tik-cli: Minimal TikTok CLI/TUI with external MPV video playback and IMV image viewer."
    )
    parser.add_argument("--play", type=str, help="Directly play a TikTok video URL in external MPV window")
    parser.add_argument("--vo", choices=["mpv"], default="mpv", help="Video output driver: 'mpv' (external hardware-accelerated window)")
    parser.add_argument("--user", type=str, help="Launch TUI directly on a specific creator's profile (@username)")
    parser.add_argument("--search", "-s", type=str, help="Launch TUI directly with keyword search (e.g. 'pakistani videos', 'naat')")
    parser.add_argument("--session", type=str, help="Authenticate directly with a TikTok sessionid cookie")
    parser.add_argument("--ttwid", type=str, help="Optional ttwid cookie for authentication")
    parser.add_argument("--logout", action="store_true", help="Remove saved session credentials")
    parser.add_argument("--dry-run", action="store_true", help="Test URL resolution or user fetch without entering TUI")
    args = parser.parse_args()

    client = TikTokClient()

    if args.logout:
        if client.logout():
            print("Successfully logged out and removed credentials from ~/.config/tik-cli/session.json")
        else:
            print("No active session to remove.")
        return

    if args.session:
        print("Authenticating with provided session ID...")
        res = client.login_by_sessionid(args.session, ttwid=args.ttwid)
        if res["success"]:
            print(f"Success: {res['message']}")
        else:
            print(f"Error: {res['message']}")
            sys.exit(1)
        return

    if args.play:
        print(f"Resolving video: {args.play}")
        video = client.resolve_video_url(args.play)
        if not video:
            print("Error: Could not resolve video metadata.")
            sys.exit(1)

        print(f"Title: {video.get('title')}")
        print(f"Author: @{video.get('author_id')}")
        print(f"Direct stream: {video.get('play_url')[:60]}...")

        if args.dry_run:
            print("Dry run complete. Exiting.")
            return

        play_video_in_terminal(video["play_url"], title=video.get("title", ""), vo_driver=args.vo)
        return

    if args.user and args.dry_run:
        print(f"Testing creator extraction for {args.user}...")
        videos = client.get_user_videos(args.user, count=3)
        print(f"Found {len(videos)} videos:")
        for v in videos:
            print(f" - {v.get('title')} ({v.get('web_url')})")
        return

    if args.search and args.dry_run:
        print(f"Searching TikTok for '{args.search}'...")
        videos = client.search_videos(args.search, count=5)
        print(f"Found {len(videos)} videos:")
        for v in videos:
            print(f" - @{v.get('author_id')}: {v.get('title')} ({v.get('web_url')})")
        return

    # Default: launch interactive TUI
    ui = TerminalUI(client)
    if args.vo:
        ui.vo_driver = args.vo
    if args.user:
        ui.load_creator(args.user)
    elif args.search:
        ui.load_search(args.search)
    ui.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting tik-cli.")
        sys.exit(0)
