import os
import json
import asyncio
import logging
import re
from datetime import datetime
from internetarchive import get_session, upload

class GhostArchiver:
    def __init__(self):
        """
        Initialize the GhostArchiver with Internet Archive session.
        Authentication is handled via ~/.config/ia.ini or environment variables.
        """
        self.session = get_session(config={
            'general': {'user_agent_suffix': 'Ghost/2.0.0 (claude-agent)'}
        })
        self.collection = "test_collection" # Default sandbox collection

    async def archive_finding(self, domain, data, metadata=None):
        """
        Archives a domain's reconnaissance data to the Internet Archive.
        
        Args:
            domain (str): The target domain.
            data (dict): The structured data to archive (e.g., reconstructed HTML, mementos).
            metadata (dict, optional): Additional metadata for the IA item.
        """
        # Create a unique identifier for the archival item
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        identifier = f"ghost_recon_{domain.replace('.', '_')}_{timestamp}"
        
        # Identifier sanitization (IA rules: alphanumeric, underscores, dashes, periods)
        identifier = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', identifier).lower()[:80]
        
        logging.info(f"[GHOST][Archiver] Archiving results for {domain} to IA identifier: {identifier}")
        
        # Prepare item-level metadata
        item_metadata = {
            "mediatype": "data",
            "collection": self.collection,
            "title": f"Ghost Reconnaissance: {domain} ({timestamp})",
            "creator": "Ghost Spectral Recon Agent",
            "subject": f"osint;reconnaissance;archival;{domain}",
            "description": f"Automated reconnaissance data captured by Ghost for {domain}.\nCaptured on: {datetime.now().isoformat()}\nScope: P2 Deep Spectral Pulse",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "original_domain": domain,
            "agent": "Ghost/2.0.0"
        }
        
        if metadata:
            item_metadata.update(metadata)

        # Create temporary file for the data
        temp_file = f"ghost_{identifier}.json"
        try:
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2)
            
            # Perform upload in a thread pool to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: upload(
                    identifier,
                    [temp_file],
                    metadata=item_metadata,
                    access_key=self.session.access_key,
                    secret_key=self.session.secret_key,
                    checksum=True,
                    retries=5,
                    headers={"X-Archive-Interactive-Priority": "1"}
                )
            )
            
            logging.info(f"[GHOST][Archiver] Successfully archived to: https://archive.org/details/{identifier}")
            return identifier
            
        except Exception as e:
            logging.error(f"[GHOST][Archiver] Failed to archive {domain}: {e}")
            return None
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

