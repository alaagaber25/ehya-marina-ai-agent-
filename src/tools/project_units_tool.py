import logging
import random
from typing import Any, Dict, List, Optional
from langchain.tools import tool
from tools.units_fetcher import fetch_units_from_api

logging.basicConfig(level=logging.INFO)

@tool
def get_project_units(
    project_id: str,
    unit_code: Optional[str] = None,
    unit_type: Optional[str] = None,
    building: Optional[str] = None,
    floor: Optional[str] = None,
    availability: Optional[str] = None,
    min_area: Optional[float] = None,
    max_area: Optional[float] = None,
    price: Optional[float] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sellable_area: Optional[float] = None,
    min_sellable_area: Optional[float] = None,
    max_sellable_area: Optional[float] = None,
    unit_type_filter: Optional[str] = None,
    price_tolerance: Optional[float] = 0.05,
    area_tolerance: Optional[float] = 0.05,
    pick_random: Optional[bool] = False
) -> List[Dict[str, Any]]:
    """
    Retrieves project units from a cached source (backed by `fetch_units_from_api("<project_id>")`).
    The data is regularly updated, so the cache is ready for quick searches and filtering.

    This tool is useful for answering real-estate queries, such as:
    - "Which units are currently available?"
    - "Show me the ones on the fifth floor."
    - "Tell me more about unit G-05."
    - "Are there any 2-bedroom units left?"
    - "Find units with price around 850,000"
    - "Show me units with sellable area around 90 sqm"

    Filtering Options:
    - `unit_code` (str): Exact unit code (e.g., "1-A"). Case-insensitive exact match.
    - `unit_type` (str): Filter by unit type (e.g., "2 BEDROOM"). Partial, case-insensitive match.
    - `building` (str): Filter by building (e.g., "BLDG 1"). Partial, case-insensitive match.
    - `floor` (str): Filter by floor (e.g., "0", "1", "2").
    - `availability` (str): Filter by availability (e.g., "available", "unlaunched").
    - `min_area` (float): Minimum unit area.
    - `max_area` (float): Maximum unit area.
    - `price` (float): Target price for approximate matching (uses price_tolerance).
    - `min_price` (float): Minimum price filter.
    - `max_price` (float): Maximum price filter.
    - `sellable_area` (float): Target sellable area for approximate matching (uses area_tolerance).
    - `min_sellable_area` (float): Minimum sellable area filter.
    - `max_sellable_area` (float): Maximum sellable area filter.
    - `unit_type_filter` (str): Exact match for type field (e.g., "C").
    - `price_tolerance` (float): Tolerance for approximate price matching (default 0.05 = 5%).
    - `area_tolerance` (float): Tolerance for approximate area matching (default 0.05 = 5%).
    - `pick_random` (bool): If True, returns a single random unit from the filtered results.

    Returns:
    - A list of units (as dictionaries) matching the applied filters.
    - If too many results are found, returns a summarized list (first 10 units + count).
    - If no units match, returns a list with an error message.
    """

    all_units = fetch_units_from_api(project_id)  # Import + Cached call

    if not all_units:
        return [{"error": "Could not fetch units from API."}]

    # Apply filters
    filtered_units = all_units
    
    # Exact match for unit code (case-insensitive)
    if unit_code:
        filtered_units = [u for u in filtered_units if u.get('code', '').lower() == unit_code.lower()]
    
    # Partial match for unit_type (case-insensitive)
    if unit_type:
        filtered_units = [u for u in filtered_units if unit_type.lower() in u.get('unit_type', '').lower()]
    
    # Partial match for building (case-insensitive)
    if building:
        filtered_units = [u for u in filtered_units if building.lower() in u.get('building', '').lower()]
    
    # Exact match for floor
    if floor:
        filtered_units = [u for u in filtered_units if u.get('floor', '').lower() == floor.lower()]
    
    # Exact match for availability
    if availability:
        filtered_units = [u for u in filtered_units if u.get('availability', '').lower() == availability.lower()]
    
    # Unit area range filters
    if min_area is not None:
        filtered_units = [u for u in filtered_units if _safe_float(u.get('unit_area', 0)) >= min_area]
    if max_area is not None:
        filtered_units = [u for u in filtered_units if _safe_float(u.get('unit_area', 0)) <= max_area]
    
    # Price filters
    if price is not None:
        # Approximate price matching with tolerance
        target_price = price
        min_price_range = target_price * (1 - price_tolerance)
        max_price_range = target_price * (1 + price_tolerance)
        filtered_units = [u for u in filtered_units 
                         if min_price_range <= _safe_float(u.get('price', 0)) <= max_price_range]
        logging.info(f"Price filter: target={target_price}, range=[{min_price_range:.2f}, {max_price_range:.2f}]")
    
    if min_price is not None:
        filtered_units = [u for u in filtered_units if _safe_float(u.get('price', 0)) >= min_price]
    
    if max_price is not None:
        filtered_units = [u for u in filtered_units if _safe_float(u.get('price', 0)) <= max_price]
    
    # Sellable area filters
    if sellable_area is not None:
        # Approximate sellable area matching with tolerance
        target_area = sellable_area
        min_area_range = target_area * (1 - area_tolerance)
        max_area_range = target_area * (1 + area_tolerance)
        filtered_units = [u for u in filtered_units 
                         if min_area_range <= _safe_float(u.get('sellable_area', 0)) <= max_area_range]
        logging.info(f"Sellable area filter: target={target_area}, range=[{min_area_range:.2f}, {max_area_range:.2f}]")
    
    if min_sellable_area is not None:
        filtered_units = [u for u in filtered_units if _safe_float(u.get('sellable_area', 0)) >= min_sellable_area]
    
    if max_sellable_area is not None:
        filtered_units = [u for u in filtered_units if _safe_float(u.get('sellable_area', 0)) <= max_sellable_area]
    
    # Exact match for type (case-insensitive)
    if unit_type_filter:
        filtered_units = [u for u in filtered_units if u.get('type', '').lower() == unit_type_filter.lower()]

    logging.info(f"Tool: Returning {len(filtered_units)} units after filtering cached data.")

    # Handle picking a random unit from the (potentially filtered) results
    if pick_random:
        if filtered_units:
            logging.info("Tool: Picking a random unit from the filtered results.")
            return [random.choice(filtered_units)] # Return as a list with one item
        else:
            return [{"error": "No units matched the criteria to pick a random one from."}]

    if len(filtered_units) > 10:
        summary = [
            {
                "code": u.get("code"),
                "unit_type": u.get("unit_type"),
                "unit_area": u.get("unit_area"),
                "sellable_area": u.get("sellable_area"),
                "price": u.get("price"),
                "availability": u.get("availability"),
                "building": u.get("building"),
                "floor": u.get("floor"),
                "type": u.get("type")
            }
            for u in filtered_units[:10]
        ]
        summary.append({"summary_message": f"Found {len(filtered_units)} units. Showing first 10."})
        return summary
    
    return filtered_units


def _safe_float(value: Any) -> float:
    """
    Safely converts a value to float, returning 0.0 if conversion fails.
    Handles string representations of numbers and None values.
    
    Args:
        value: The value to convert to float
        
    Returns:
        float: The converted value or 0.0 if conversion fails
    """
    if value is None:
        return 0.0
    
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0