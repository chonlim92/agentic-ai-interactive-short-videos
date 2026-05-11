# Publish Episode

## When to Use
- User asks to publish a finished episode to the website
- Publisher needs to deploy episode with voting poll
- Episode is fully composed and approved

## Procedure
1. Verify final episode exists: `data/episodes/<ep_number>/final/episode_<n>.mp4`
2. Read publish spec: `data/episodes/<ep_number>/publish.yaml`
3. Generate thumbnail if not exists
4. Run publishing:
   ```bash
   python agents/publish_site.py --episode <ep_number>
   ```
5. Verify episode page is live on site
6. Confirm voting poll is active

## Parameters
- `--episode` — Episode number to publish
- `--draft` — Deploy as draft (not public). Default: false
- `--schedule` — Schedule publish time (ISO format). Default: immediate
