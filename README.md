# CartScout

Scrape a League of Legends patch into structured JSON with:

    python src/scrape_patch.py 26.14

The scraper reuses cached HTML from data/raw when available. Pass --refresh
to download the page again. Output is written to data/processed.

## Run Patch Notes Buddy

Install the Python packages:

    python -m pip install -r requirements.txt

Add `OPENAI_API_KEY` to `.env`, then start the backend from the project root:

    python -m uvicorn src.api:app --reload

In a second terminal, start the React app:

    cd frontend
    npm run dev

The frontend runs at `http://localhost:5173` and proxies `/api` requests to the
backend at `http://127.0.0.1:8000`.
