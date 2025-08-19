import csv
import logging
import os
from datetime import datetime

from langchain.tools import tool

logging.basicConfig(level=logging.INFO)

LEADS_FILE_PATH = os.path.relpath(
    os.path.join(os.path.dirname(__file__), "tool_outputs", "leads.csv")
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
        header = ["name", "phone", "unit_code", "notes", "timestamp"]

        # Prepare the data row
        from datetime import datetime

        lead_data = {
            "name": name,
            "phone": phone,
            "unit_code": unit_code,
            "notes": notes,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Check if file exists to write header only once
        file_exists = os.path.isfile(LEADS_FILE_PATH)

        with open(LEADS_FILE_PATH, "a", newline="", encoding="utf-8-sig") as f:
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
