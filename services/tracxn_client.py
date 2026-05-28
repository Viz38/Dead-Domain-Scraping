import logging
import httpx
import asyncio
from utils.tracxn_api import get_tracxn_config

class TracxnClient:
    def __init__(self):
        self.config = get_tracxn_config()
        self.endpoint = self.config.get("endpoint")
        self.headers = self.config.get("headers", {})
        self.payloads = self.config.get("payloads", [])
        
    async def fetch_domains(self, target_count=200, payload_override=None, start_from=0) -> tuple:
        """
        Executes the API request to Tracxn to fetch domains in bulk.
        Handles pagination (size and from) to grab the target_count.
        Returns: (results_list, new_offset, is_exhausted)
        """
        if not self.endpoint or "..." in self.endpoint:
            logging.error("[TracxnClient] Endpoint is not properly configured in .env.")
            return [], start_from, True
            
        all_results = []
        current_from = start_from
        is_exhausted = False
        
        # Use provided payload or fallback to the first one in the list (if any)
        base_payload = payload_override if payload_override else (self.payloads[0]["payload"] if self.payloads else {})
        batch_size = base_payload.get("size", 100)
        
        async with httpx.AsyncClient() as client:
            while len(all_results) < target_count:
                current_payload = base_payload.copy()
                current_payload["from"] = current_from
                
                # Ensure we don't over-fetch on the last batch
                remaining = target_count - len(all_results)
                if remaining < batch_size:
                    current_payload["size"] = remaining
                else:
                    current_payload["size"] = batch_size

                payload_size_bytes = len(str(current_payload).encode('utf-8'))
                
                logging.info(f"[TracxnClient] Sending POST to {self.endpoint} | from={current_payload['from']}, size={current_payload['size']} | Payload Size: {payload_size_bytes} bytes")
                
                try:
                    response = await client.post(
                        self.endpoint,
                        json=current_payload,
                        headers=self.headers,
                        timeout=30.0
                    )
                    response.raise_for_status()
                    logging.info(f"[TracxnClient] Response Status: {response.status_code}")
                    data = response.json()
                    
                    parsed_batch = self._parse_response(data)
                    logging.info(f"[TracxnClient] Parsed {len(parsed_batch)} domains from response.")
                    
                    if not parsed_batch:
                        logging.info("[TracxnClient] No more results returned by the API.")
                        is_exhausted = True
                        break
                        
                    all_results.extend(parsed_batch)
                    current_from += len(parsed_batch)
                    
                    # If we got fewer results than requested, we've hit the end
                    if len(parsed_batch) < current_payload["size"]:
                        is_exhausted = True
                        break
                        
                except httpx.HTTPStatusError as e:
                    logging.error(f"[TracxnClient] HTTP Error: {e.response.status_code}")
                    is_exhausted = True
                    break
                except Exception as e:
                    logging.error(f"[TracxnClient] Request failed Exception: {str(e)}")
                    is_exhausted = True
                    break

        return all_results[:target_count], current_from, is_exhausted

    def _parse_response(self, raw_data: dict) -> list:
        """
        Parses the raw Tracxn API response.
        Extracts the 'domain' field from the 'result' array.
        """
        domains = []
        if "result" in raw_data and isinstance(raw_data["result"], list):
            for item in raw_data["result"]:
                domain = item.get("domain")
                if domain:
                    domains.append(domain)
            return domains
        
        logging.warning("[TracxnClient] Unrecognized response format, could not extract domains.")
        return []

if __name__ == "__main__":
    # Configure logging for standalone testing
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    async def run_test():
        client = TracxnClient()
        logging.info("Starting Tracxn API Test to fetch 200 domains...")
        results, new_offset, is_exhausted = await client.fetch_domains(target_count=200)
        logging.info(f"Test complete. Total domains grabbed: {len(results)}. New Offset: {new_offset}. Exhausted: {is_exhausted}")
        if results:
            print("First item sample:")
            print(results[0])
            
    asyncio.run(run_test())
