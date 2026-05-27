import os
import json
import logging
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

def get_tracxn_config():
    """
    Securely fetches the Tracxn API configuration from the .env file.
    Parses JSON strings into Python dictionaries for Headers and Payload.
    """
    endpoint = os.getenv("TRACXN_API_ENDPOINT")
    
    headers_str = os.getenv("TRACXN_API_HEADERS", "{}")
    payload_str = os.getenv("TRACXN_API_PAYLOAD", "{}")
    
    try:
        headers = json.loads(headers_str)
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse TRACXN_API_HEADERS from .env: {e}")
        headers = {}
        
    payloads = []
    for i in range(1, 4):
        p_str = os.getenv(f"TRACXN_API_PAYLOAD_{i}", "{}")
        pct_str = os.getenv(f"Pass{i}Limit", "0")
        try:
            pct = float(pct_str)
            p_json = json.loads(p_str)
            if p_json:
                payloads.append({"payload": p_json, "pct": pct})
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse TRACXN_API_PAYLOAD_{i} from .env: {e}")
        except ValueError:
            logging.error(f"Invalid percentage for Pass{i}Limit")
            
    return {
        "endpoint": endpoint,
        "headers": headers,
        "payloads": payloads
    }

# Example Usage:
# if __name__ == "__main__":
#     config = get_tracxn_config()
#     print("Endpoint loaded securely.")
#     print(f"Headers type: {type(config['headers'])}")
