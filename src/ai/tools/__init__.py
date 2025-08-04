import logging
import random
import cloudscraper
import csv 
from langchain.tools import tool
from typing import Optional, List, Dict, Any
import json

import time
from requests.exceptions import RequestException, ConnectionError, Timeout

logging.basicConfig(level=logging.INFO)

# --- Caching Mechanism ---
# We will ONLY use the last_search_results. The global unit_cache is removed to prevent data overwriting bugs.
last_search_results: List[Dict[str, Any]] = []

def clear_unit_cache():
    """Clears the last search results cache for a new session."""
    global last_search_results
    last_search_results = []
    logging.info("Tool Cache: Last search results cache has been cleared.")

@tool
def get_project_units(
    project_id: str,
    unit_code: Optional[str] = None,
    unit_type: Optional[str] = None,
    building: Optional[str] = None,
    floor: Optional[str] = None,
    availability: Optional[str] = None,
    min_area: Optional[float] = None,
    max_area: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    **CRITICAL: Use this tool for the FIRST or INITIAL search for units.**
    This tool connects to the main database to fetch a fresh list of properties based on the user's initial criteria.

    You MUST use this tool when:
    - The user starts a new conversation and asks for any type of unit.
    - The user's request is the beginning of a search and there are no previous results in memory.
    - The user explicitly asks to start a new or different search.

    Example: If the user's first message is "I want to see available units in building 1 on the third floor," you MUST use this tool, not search_units_in_memory.
    """
    global last_search_results
    api_url = f"https://realestate-api.voom.cc/api/v1/companies/{project_id}/units"

    retries = 3
    for attempt in range(retries):
        try:
            logging.info(f"Tool: Attempt {attempt + 1}/{retries} to fetch data from {api_url}")
            response = scraper.get(api_url, timeout=15)
            response.raise_for_status()

            all_units = response.json().get("data", {}).get("units", [])
            logging.info(f"Tool: Retrieved {len(all_units)} units")

            # Apply filters
            filtered_units = all_units
            if unit_code:
                filtered_units = [u for u in filtered_units if u.get('code', '').lower() == unit_code.lower()]
            if unit_type:
                filtered_units = [u for u in filtered_units if unit_type.lower() in u.get('unit_type', '').lower()]
            if building:
                filtered_units = [u for u in filtered_units if u.get('building', '').lower() == building.lower()]
            if floor:
                filtered_units = [u for u in filtered_units if u.get('floor', '').lower() == floor.lower()]
            if availability:
                filtered_units = [u for u in filtered_units if u.get('availability', '').lower() == availability.lower()]
            if min_area is not None:
                filtered_units = [u for u in filtered_units if float(u.get('unit_area', 0)) >= min_area]
            if max_area is not None:
                filtered_units = [u for u in filtered_units if float(u.get('unit_area', 0)) <= max_area]

            last_search_results = filtered_units
            logging.info(f"Tool: Cached {len(filtered_units)} filtered units")

            if len(filtered_units) > 10:
                summary = [
                    {
                        "code": u.get("code"),
                        "unit_type": u.get("unit_type"),
                        "unit_area": u.get("unit_area"),
                        "availability": u.get("availability"),
                        "building": u.get("building"),
                        "floor": u.get("floor")
                    }
                    for u in filtered_units[:10]
                ]
                summary.append({"summary_message": f"Found {len(filtered_units)} units. Showing first 10."})
                return summary

            return filtered_units

        except (ConnectionError, Timeout, RequestException) as e:
            logging.warning(f"Tool: Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                wait = 2 ** attempt
                logging.info(f"Tool: Retrying in {wait} seconds...")
                time.sleep(wait)
            else:
                logging.error("Tool: All retries failed.")
                return [{"error": f"Network issue. Could not retrieve data after {retries} attempts. Error: {str(e)}"}]
        except Exception as ex:
            logging.exception("Tool: Unexpected error occurred")
            return [{"error": f"Unexpected error: {str(ex)}"}]

    return [{"error": "Unhandled error occurred while fetching project units."}]

@tool
def search_units_in_memory(
    unit_code: Optional[str] = None,
    floor: Optional[str] = None,
    building: Optional[str] = None,
    availability: Optional[str] = None,
    unit_type: Optional[str] = None,
    min_area: Optional[float] = None,
    max_area: Optional[float] = None,
    pick_random: bool = False
) -> List[Dict[str, Any]]:
    """
    Filters, queries, or selects from a list of units previously fetched by `get_project_units`.

    **CRITICAL RULE: This tool MUST ONLY be used for follow-up questions to refine results that are
    already in memory from a successful `get_project_units` call in a previous turn.**
    DO NOT use this tool for a user's initial search query. It will fail if no units have been fetched first.

    This tool is essential for answering questions like:
    - "Okay, which of those are available?"
    - "Show me the ones on the fifth floor from that list."
    - "Can you tell me more about unit G-05?"
    - "Are any of the 2-bedroom units left?"

    Supported parameters:
    - `unit_code`: Returns a specific unit by code (exact match).
    - `floor`: Filters the last results to show only units on that floor.
    - `building`: Filters results to a specific building.
    - `availability`: Filters by availability status (e.g., `"available"`).
    - `unit_type`: Filters by unit type (e.g., `"2 BEDROOM"`).
    - `min_area` and `max_area`: Filters based on unit area range.
    - `pick_random`: If set to `True`, returns a single random unit from the filtered results.

    This tool must only be used **after** a previous search result exists in memory. If no prior results are available, it returns an appropriate error message.
    """

    global last_search_results
    
    if not last_search_results:
        logging.warning("Tool: Cannot search memory because the last search result is empty.")
        return [{"error": "I don't have any previous search results to filter. Please start a new search."}]

    # Start with the last known results
    results_to_filter = last_search_results

    # Handle the specific case of asking for a single unit by code
    if unit_code:
        logging.info(f"Tool: Searching for specific unit '{unit_code}' in LAST SEARCH RESULTS.")
        for unit in results_to_filter:
            if unit.get('code', '').lower() == unit_code.lower():
                logging.info(f"Tool: Found unit '{unit_code}'.")
                return [unit] # Return as a list with one item
        return [{"error": f"Sorry, I couldn't find unit '{unit_code}' in the results I just showed you."}]

    # Apply filters if provided
    if floor:
        results_to_filter = [u for u in results_to_filter if u.get('floor') == floor]
    if building:
        results_to_filter = [u for u in results_to_filter if u.get('building', '').lower() == building.lower()]
    if availability:
        results_to_filter = [u for u in results_to_filter if u.get('availability', '').lower() == availability.lower()]
    if unit_type:
        results_to_filter = [u for u in results_to_filter if unit_type.lower() in u.get('unit_type', '').lower()]
    if min_area is not None:
        results_to_filter = [u for u in results_to_filter if float(u.get('unit_area', 0)) >= min_area]
    if max_area is not None:
        results_to_filter = [u for u in results_to_filter if float(u.get('unit_area', 0)) <= max_area]

    # Handle picking a random unit from the (potentially filtered) results
    if pick_random:
        if results_to_filter:
            logging.info("Tool: Picking a random unit from the filtered results.")
            return [random.choice(results_to_filter)] # Return as a list with one item
        else:
            return [{"error": "No units matched the criteria to pick a random one from."}]

    logging.info(f"Tool: Returning {len(results_to_filter)} units after filtering memory.")
    return results_to_filter


last_search_results: List[Dict[str, Any]] = []
scraper = cloudscraper.create_scraper(
    browser={"custom": "ScraperBot/1.0"}
)

@tool
def save_lead(name: str, phone: str, unit_code: str, notes: str) -> str:
    """
    Saves the information of an interested user (lead) for follow-up by a sales agent.

    - The user expresses **strong interest** in a specific unit and agrees to be contacted.
    - The **unit is not available**, and the user wants to be contacted when it becomes available.
    - The user explicitly requests to be **connected with customer service or support**.

    Parameters:
    - name (str): The user's full name.
    - phone (str): The user's phone number.
    - unit_code (str): The code of the unit the user is interested in.
    - notes (str): *Auto-generated summary** of the user’s intent and relevant chat history. 

    Returns:
    - A success or error message based on whether the lead was saved successfully.
    """

    logging.info(f"Tool: Saving lead - Name: {name}, Phone: {phone}, Unit: {unit_code}")
    try:
        # Define the header for the CSV file
        header = ['name', 'phone', 'unit_code', 'notes', 'timestamp']
        
        # Prepare the data row
        from datetime import datetime
        lead_data = {
            'name': name,
            'phone': phone,
            'unit_code': unit_code,
            'notes': notes,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Check if file exists to write header only once
        import os
        file_exists = os.path.isfile(r'src/ai/tools/data/leads.csv')

        with open(r'src/ai/tools/data/leads.csv', 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=header)
            if not file_exists:
                writer.writeheader()  # Write header if file is new
            writer.writerow(lead_data)
            
        success_message = f"Successfully saved lead for {name}. A consultant will contact them shortly about unit {unit_code}."
        logging.info(success_message)
        return success_message
    except Exception as e:
        error_message = f"An error occurred while saving the lead: {e}"
        logging.error(error_message)
        return error_message


