#!/bin/bash
# Daily refresh: ingest user-submitted sources, scrape built-in houses, rebuild static export.
# Lebriz archive import runs weekly (Mondays) or with --lebriz; it is resumable and cached (lebriz_cache/).
# Cron: 0 8 * * * /workspace/auction-hub/refresh.sh >> /workspace/auction-hub/refresh.log 2>&1
cd "$(dirname "$0")" && date
git pull --ff-only --quiet 2>/dev/null || echo "git pull skipped"  # pick up links added by the GitHub Action
python3 add_sources.py || echo "add_sources failed (continuing)"
python3 scrape.py
# Finished MüzayedeApp auctions (these sites refuse GitHub, so history is collected here). Incremental, max ~40 min.
timeout 45m python3 history_mapp.py --since 2000-01-01 --minutes 40 || echo "history_mapp incomplete (continues next run)"
if [ "$1" = "--lebriz" ] || [ "$(date +%u)" = "1" ]; then timeout 3h python3 lebriz.py || echo "lebriz import incomplete (resumes next run)"; fi
# Copy new images into the private bucket so they outlive the auction (resumes where it stopped; needs GCS_KEY).
timeout 35m python3 mirror_images.py --minutes 30 || echo "image mirror incomplete (continues next run)"
python3 lebriz_export.py
python3 export.py
# Per-artist shards of finished auctions (data/artist/*.json + data/artist_index.json), so phones never load the whole archive.
python3 shard_past.py || echo "shard_past failed (site falls back to the full past files)"
# One light index of every work, for the Arsiv page (data/archive.json, data/archive_text.json).
python3 build_archive.py || echo "build_archive failed (Arsiv keeps the previous index)"
