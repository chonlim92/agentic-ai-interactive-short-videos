# Tally Votes

## When to Use
- User asks to check or collect audience vote results
- Community manager needs to summarize voting outcomes
- Vote deadline has passed and results are needed for next episode

## Procedure
1. Check vote deadline has passed for the episode
2. Run vote collection:
   ```bash
   python agents/tally_votes.py --episode <ep_number>
   ```
3. Review results in `data/episodes/<ep_number>/engagement.yaml`
4. Report winning option and vote breakdown
5. Notify @writer of the audience's choice for the next episode

## Parameters
- `--episode` — Episode number to tally votes for
- `--format` — Output format (yaml, json, summary). Default: yaml
