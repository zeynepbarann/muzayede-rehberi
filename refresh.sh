#!/bin/bash
# Daily refresh: scrape auctions, rebuild static export.
# Lebriz archive import runs weekly (Mondays) or with --lebriz; it is resumable and cached (lebriz_cache/).
# Cron: 0 8 * * * /workspace/auction-hub/refresh.sh >> /workspace/auction-hub/refresh.log 2>&1
cd "$(dirname "$0")" && date
python3 scrape.py
if [ "$1" = "--lebriz" ] || [ "$(date +%u)" = "1" ]; then timeout 3h python3 lebriz.py || echo "lebriz import incomplete (resumes next run)"; fi
python3 lebriz_export.py
python3 export.py
