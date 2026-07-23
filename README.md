# CartScout

Scrape a League of Legends patch into structured JSON with:

    python src/scrape_patch.py 26.14

The scraper reuses cached HTML from data/raw when available. Pass --refresh
to download the page again. Output is written to data/processed.
