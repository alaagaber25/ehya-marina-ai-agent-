import cloudscraper
import functools
import logging
from typing import Any, Dict, List, Optional
from requests.exceptions import ConnectionError, RequestException, Timeout
import time

logging.basicConfig(level=logging.INFO)

# Initialize the scraper once
# We have use cloudscraper to handle potential bot detection because it can simulate a real browser environment which the requests library cannot.
scraper = cloudscraper.create_scraper(
    browser={"custom": "ScraperBot/1.0"}
)

# --- Cached fetch function ---
@functools.cache
def fetch_units_from_api(project_id: str) -> List[Dict[str, Any]]:
    """
    Fetch all units for a given project_id once and cache them.
    Any repeated calls with the same project_id will return from cache.
    """
    api_url = f"https://realestate-api.voom.cc/api/v1/companies/{project_id}/units"
    retries = 3

    for attempt in range(retries):
        try:
            logging.info(f"API: Attempt {attempt + 1}/{retries} to fetch data from {api_url}")
            response = scraper.get(api_url, timeout=15)
            response.raise_for_status()
            all_units = response.json().get("data", {}).get("units", [])
            logging.info(f"API: Retrieved {len(all_units)} units for project {project_id}")
            return all_units

        except (ConnectionError, Timeout, RequestException) as e:
            logging.warning(f"API: Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                wait = 2**attempt
                logging.info(f"API: Retrying in {wait} seconds...")
                time.sleep(wait)
            else:
                logging.error("API: All retries failed.")
                return []

    return []
