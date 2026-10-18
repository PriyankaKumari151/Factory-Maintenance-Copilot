"""Separate network client: bounded GET retries, no blind ticket POST retries."""
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class InventoryClient:
    def __init__(self):
        self.base = os.getenv('PLATFORM_URL', 'http://127.0.0.1:8001').rstrip('/')
        self.session = requests.Session()
        retry = Retry(total=2, backoff_factor=0.2, status_forcelist=[429, 502, 503, 504],
                      allowed_methods=['GET'], respect_retry_after_header=False)
        self.session.mount('http://', HTTPAdapter(max_retries=retry))
        self.session.mount('https://', HTTPAdapter(max_retries=retry))

    def get_part(self, part_id):
        try:
            r = self.session.get(f'{self.base}/parts/{part_id}', timeout=(2, 3))
            if r.status_code == 404:
                return {'part_id': part_id, 'error': 'Part not found'}
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            return {'part_id': part_id, 'error': 'Inventory service unavailable'}

    def create_ticket(self, ticket, idempotency_key):
        r = self.session.post(f'{self.base}/tickets', json=ticket,
                              headers={'Idempotency-Key': idempotency_key}, timeout=(2, 5))
        r.raise_for_status()
        return r.json()
