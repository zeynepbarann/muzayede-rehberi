#!/bin/bash
# Daily refresh: scrape all sites, rebuild static export. Cron: 0 8 * * * /workspace/auction-hub/refresh.sh >> /workspace/auction-hub/refresh.log 2>&1
cd "$(dirname "$0")" && date && python3 scrape.py && python3 export.py
