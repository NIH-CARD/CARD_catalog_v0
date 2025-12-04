#!/bin/bash
cd /mnt/c/Users/mike1/Projects/CARD_catalog/scrapers
source .env
python3 scrape_github.py --start 22 --end 23 --output ../tables/gits_gnpc_20251202.tsv
