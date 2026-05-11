"""Tally Audience Votes

Collects and summarizes audience voting results from the Next.js site API.

Usage:
    python agents/tally_votes.py --episode <number>
    python agents/tally_votes.py --episode 1 --format summary
    python agents/tally_votes.py --episode 1 --close  # Close voting
"""

# Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
# Licensed under CC BY-NC 4.0. See LICENSE for details.

# Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
# Licensed under CC BY-NC 4.0. See LICENSE for details.

import argparse
import os

import requests
from common import episode_dir, load_env, save_yaml, setup_logging

load_env()
log = setup_logging("tally_votes")


def get_site_url() -> str:
    """Get the site URL from environment."""
    return os.getenv("SITE_URL", "http://localhost:3000")


def collect_votes(episode_number: int) -> dict:
    """
    Collect votes from the Next.js site API.
    Falls back to placeholder data if the site is unreachable.
    """
    log.info(f"Collecting votes for Episode {episode_number}...")
    site_url = get_site_url()
    api_url = f"{site_url}/api/episodes/{episode_number}/results"

    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()

        results = {
            "vote_results": {
                "episode": data["episode_number"],
                "total_votes": data["total_votes"],
                "options": [
                    {
                        "text": r["label"],
                        "votes": r["votes"],
                        "percentage": r["percentage"],
                    }
                    for r in data["results"]
                ],
                "winner": data["winner"],
                "voting_open": data["voting_open"],
            }
        }
        log.info(f"Fetched {data['total_votes']} votes from API")
        return results

    except requests.ConnectionError:
        log.warning(f"Cannot reach site at {site_url}. Using placeholder data.")
        return _placeholder_results(episode_number)
    except requests.HTTPError as e:
        log.warning(f"API error: {e}. Using placeholder data.")
        return _placeholder_results(episode_number)


def close_voting(episode_number: int) -> bool:
    """Close voting for an episode via the API."""
    site_url = get_site_url()
    api_url = f"{site_url}/api/episodes/{episode_number}/results"

    try:
        response = requests.post(
            api_url,
            json={"action": "close_voting"},
            timeout=10,
        )
        response.raise_for_status()
        log.info(f"Voting closed for Episode {episode_number}")
        return True
    except requests.RequestException as e:
        log.error(f"Failed to close voting: {e}")
        return False


def _placeholder_results(episode_number: int) -> dict:
    """Placeholder results when API is unreachable."""
    return {
        "vote_results": {
            "episode": episode_number,
            "total_votes": 0,
            "options": [],
            "winner": None,
            "voting_open": False,
            "notes": "Placeholder -- site API unreachable",
        }
    }


def save_results(episode_number: int, results: dict, fmt: str = "yaml"):
    """Save vote results to episode data."""
    output_path = episode_dir(episode_number) / "engagement.yaml"
    save_yaml(results, output_path)
    log.info(f"Results saved to {output_path}")

    if fmt == "summary":
        vr = results["vote_results"]
        log.info(f"--- Vote Summary for Episode {vr['episode']} ---")
        log.info(f"Total votes: {vr['total_votes']}")
        if vr["options"]:
            for opt in vr["options"]:
                log.info(f"  {opt['text']}: {opt['votes']} ({opt['percentage']}%)")
            log.info(f"Winner: {vr['winner']}")
        else:
            log.info("No votes recorded yet.")


def main():
    parser = argparse.ArgumentParser(description="Tally audience votes")
    parser.add_argument("--episode", type=int, required=True, help="Episode number")
    parser.add_argument("--story", type=str, default=None, help="Story slug")
    parser.add_argument(
        "--format",
        type=str,
        default="yaml",
        choices=["yaml", "json", "summary"],
    )
    parser.add_argument("--close", action="store_true", help="Close voting for the episode")
    args = parser.parse_args()

    if args.close:
        close_voting(args.episode)
        return

    results = collect_votes(args.episode)
    save_results(args.episode, results, fmt=args.format)


if __name__ == "__main__":
    main()
