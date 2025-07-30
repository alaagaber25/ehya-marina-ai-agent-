import logging
import random
import cloudscraper
import csv 
from langchain.tools import tool
from typing import Optional, List, Dict, Any

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
    Filters the most recent unit search results stored in memory.

    Use this tool to handle **follow-up queries** after an initial unit search. It allows you to answer user questions such as:
    - "Which of these units is available?"
    - "Which of them is on the fifth floor?"
    - "Which ones are in Building 1?"
    - "Do you have any unit that matches my filters?"

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
    Fetches and filters unit data from the main database for ALL NEW searches.
    This tool populates the memory with its findings for follow-up questions.
    """
    global last_search_results
    scraper = cloudscraper.create_scraper()
    
    api_url = f"https://realestate-api.voom.cc/api/v1/companies/{project_id}/units"
    logging.info(f"Tool: Fetching all unit data for project '{project_id}'...")

    try:
        response = scraper.get(api_url, timeout=30)
        response.raise_for_status()
        all_units = response.json().get("data", {}).get("units", [])
        logging.info(f"Tool: Successfully fetched {len(all_units)} total units.")

        
        # --- Filtering Logic ---
        filtered_units = all_units
        if unit_code:
            filtered_units = [u for u in filtered_units if u.get('code', '').lower() == unit_code.lower()]
        if unit_type:
            filtered_units = [u for u in filtered_units if unit_type.lower() in u.get('unit_type', '').lower()]
        if building:
            filtered_units = [u for u in filtered_units if u.get('building', '').lower() == building.lower()]
        if availability:
            filtered_units = [u for u in filtered_units if u.get('availability', '').lower() == availability.lower()]
        if min_area is not None:
            filtered_units = [u for u in filtered_units if float(u.get('unit_area', 0)) >= min_area]
        if max_area is not None:
            filtered_units = [u for u in filtered_units if float(u.get('unit_area', 0)) <= max_area]

        # --- CRITICAL FIX: Update the 'last_search_results' cache with the FULL, filtered data ---
        last_search_results = filtered_units
        logging.info(f"Tool: 'Last Search' cache updated with {len(last_search_results)} units. This is now the source of truth for follow-ups.")

        # --- Summarization Logic ---
        if len(filtered_units) > 10:
            logging.info("Tool: Result is large. Creating a summary.")
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
            summary.append({"summary_message": f"Found {len(filtered_units)} units. Showing a sample of the first 10."})
            return summary

        return filtered_units

    except Exception as e:
        logging.error(f"Tool: Failed to fetch or process data: {e}")
        return [{"error": f"An error occurred: {e}"}]



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
        file_exists = os.path.isfile('data/leads.csv')
        
        with open('data/leads.csv', 'a', newline='', encoding='utf-8-sig') as f:
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



@tool
def navigate_to_page(url: str) -> str:
    """Simulates navigation to a specific page within the website."""
    logging.info(f"Tool: Simulating navigation to URL: {url}")
    return f"Navigated to {url}."

@tool
def click_element(selector: str) -> str:
    """Simulates clicking on a specific element on the page."""
    logging.info(f"Tool: Simulating click on element: {selector}")
    return f"Clicked element with selector '{selector}'."
