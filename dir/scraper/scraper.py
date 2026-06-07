import os
import json
import time
import random
import logging
import re
import socket
import atexit
from datetime import datetime
from urllib.parse import urlparse, quote_plus
import requests
from DrissionPage import ChromiumPage, ChromiumOptions

# Configure enterprise audit logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)


class EnterprisePricingPipeline:
    def __init__(self):
        # 1. EDIT THIS PATH IF YOUR DATA FOLDER CHANGES
        self.db_path = "../list/products.json"

        # 2. EDIT YOUR PROFIT MARGIN HERE (0.20 = 20%)
        self.profit_margin = 0.20

        self.allowed_domains = ["amazon.com", "aliexpress.com", "temu.com"]

        # 3. EDIT OR PROVIDE YOUR OPENROUTER API KEY HERE
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "your_openrouter_api_key_here")
        self.model_name = "meta-llama/llama-3-8b-instruct:free"
        self._browser = None

        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0"
        ]

        atexit.register(self.close_pipeline_assets)

    # ------------------------------------------------------------------
    # Browser management
    # ------------------------------------------------------------------

    def _find_free_port(self) -> int:
        """Finds an available local port for the browser debugging interface."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return s.getsockname()[1]

    def _get_browser(self) -> ChromiumPage:
        """Lazily initializes and configures a single persistent browser instance."""
        if not self._browser:
            logging.info("Initializing persistent automated browser instance...")

            import subprocess
            import shutil

            # Kill any zombie chromium-browser processes from previous runs
            subprocess.run(["pkill", "-f", "chromium-browser"], stderr=subprocess.DEVNULL)
            time.sleep(1.0)

            # Wipe stale profile/lock files that block a clean connection
            profile_path = "/tmp/drission_user_profile"
            if os.path.exists(profile_path):
                shutil.rmtree(profile_path, ignore_errors=True)
            os.makedirs(profile_path, exist_ok=True)

            co = ChromiumOptions()
            
            # Let DrissionPage handle port assignment natively
            co.auto_port() 

            co.set_browser_path("/usr/bin/chromium-browser")
            co.set_user_data_path(profile_path)

            # Use DrissionPage's native headless toggle instead of manual arguments
            co.headless(True)

            # Keep the essential Linux container arguments
            co.set_argument('--no-sandbox')
            co.set_argument('--disable-gpu')
            co.set_argument('--disable-dev-shm-usage')
            co.set_argument('--disable-software-rasterizer')
            co.set_argument('--disable-extensions')
            co.set_argument('--single-process')

            self._browser = ChromiumPage(addr_or_opts=co)

        return self._browser

    def close_pipeline_assets(self):
        """Gracefully terminates the active browser driver."""
        if self._browser:
            try:
                self._browser.quit()
                logging.info("Persistent browser driver shut down cleanly.")
            except Exception as e:
                logging.error(f"Error during browser teardown: {e}")
            finally:
                self._browser = None

    # ------------------------------------------------------------------
    # URL / query utilities
    # ------------------------------------------------------------------

    def verify_domain_compliance(self, url: str) -> bool:
        """Validates that destination URLs match the approved domain whitelist."""
        try:
            parsed = urlparse(url.lower())
            domain = parsed.netloc.lstrip("www.")
            return any(target in domain for target in self.allowed_domains)
        except Exception:
            return False

    def sanitize_and_tokenize_query(self, raw_query: str) -> str:
        """Normalises erratic product strings into clean search keywords."""
        tokens = [t.strip() for t in re.split(r'[-_,\s\.\/\\]+', raw_query) if t.strip()]
        return " ".join(tokens)

    # ------------------------------------------------------------------
    # Discovery & scraping
    # ------------------------------------------------------------------

    def discover_vendor_assets(self, market_query: str, payload_depth: int = 3) -> list:
        """Searches Google for product URLs on whitelisted vendor domains."""
        keywords = self.sanitize_and_tokenize_query(market_query)
        logging.info(f"Initiating asset discovery for: '{keywords}'")

        matched_endpoints = []
        try:
            browser = self._get_browser()
            browser.set.user_agent(random.choice(self.user_agents))

            structured_query = f"(site:amazon.com OR site:aliexpress.com OR site:temu.com) {keywords}"
            target_url = f"https://www.google.com/search?q={quote_plus(structured_query)}"

            browser.get(target_url)
            time.sleep(random.uniform(3.5, 6.5))

            for anchor in browser.eles('t:a'):
                href = anchor.attr('href')
                if (
                    href
                    and self.verify_domain_compliance(href)
                    and href not in matched_endpoints
                    and any(p in href for p in ["/dp/", "/item/", "/goods-"])
                ):
                    matched_endpoints.append(href)
                    if len(matched_endpoints) >= payload_depth:
                        break

        except Exception as e:
            logging.error(f"Discovery automation exception: {e}")

        return matched_endpoints

    def extract_clean_payload(self, url: str) -> str | None:
        """Extracts visible page text from a whitelisted product URL."""
        if not self.verify_domain_compliance(url):
            return None

        try:
            browser = self._get_browser()
            browser.set.user_agent(random.choice(self.user_agents))
            browser.get(url)
            time.sleep(random.uniform(2.5, 5.0))
            return browser.text
        except Exception as e:
            logging.error(f"Failed to resolve remote DOM: {e}")
            return None

    # ------------------------------------------------------------------
    # LLM integration
    # ------------------------------------------------------------------

    def safe_llm_post_with_backoff(self, payload: dict) -> str | None:
        """Posts to the LLM API with exponential backoff on rate-limit errors."""
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        base_delay = 2.0

        for attempt in range(5):
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=25)

                if res.status_code == 429:
                    sleep_time = (base_delay ** attempt) + random.uniform(0.5, 1.5)
                    logging.warning(f"Rate limit hit. Backing off for {sleep_time:.2f}s...")
                    time.sleep(sleep_time)
                    continue

                res.raise_for_status()
                return res.json()['choices'][0]['message']['content']

            except requests.exceptions.RequestException as e:
                logging.error(f"Network error on attempt {attempt + 1}: {e}")
                time.sleep(base_delay * (attempt + 1))

        logging.critical("API request failed after maximum retries.")
        return None

    def analyze_payload_metrics(self, page_text: str) -> dict | None:
        """Sends page text to the LLM and returns a structured product JSON."""
        system_directive = (
            "You are an enterprise data transformation layer. Analyze the provided product metrics. "
            "Return exclusively a minimized JSON entity matching this specification exactly. "
            "Do not include any conversational text, markdown wrapping, or markdown code blocks.\n\n"
            "SCHEMA:\n"
            "{\n"
            '  "title": "String",\n'
            '  "scraped_price": Float,\n'
            '  "regular_market_price": Float,\n'
            '  "genre": "Furniture" | "Consoles" | "Appliances",\n'
            '  "condition": "String",\n'
            '  "specifications": "String",\n'
            '  "review_summary": "String",\n'
            '  "is_good_deal": Boolean\n'
            "}"
        )

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_directive},
                {"role": "user", "content": page_text[:8000]}
            ],
            "response_format": {"type": "json_object"}
        }

        raw = self.safe_llm_post_with_backoff(payload)
        if not raw:
            return None

        try:
            clean = raw.strip()
            if clean.startswith("```"):
                clean = re.sub(r'^```json\s*|```$', '', clean, flags=re.IGNORECASE).strip()

            parsed = json.loads(clean)

            for key in ("scraped_price", "regular_market_price"):
                if key in parsed and isinstance(parsed[key], str):
                    match = re.search(r'\d+(\.\d+)?', parsed[key])
                    parsed[key] = float(match.group()) if match else 0.0

            return parsed

        except (json.JSONDecodeError, ValueError, Exception) as e:
            logging.error(f"Failed to parse LLM response: {e}")
            return None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def execute_deduplication_sync(self, proposed_record: dict):
        """Appends a record to the local JSON store, deduplicating by title similarity."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        if not os.path.exists(self.db_path):
            with open(self.db_path, "w") as f:
                json.dump([], f)

        try:
            with open(self.db_path, "r") as f:
                dataset = json.load(f)
        except json.JSONDecodeError:
            dataset = []

        dataset.append(proposed_record)
        dataset.sort(key=lambda x: float(x.get("scraped_price", float('inf'))))

        optimized_pool = []
        for candidate in dataset:
            candidate_tokens = set(candidate.get("title", "").lower().split())
            is_duplicate = False

            for accepted in optimized_pool:
                if accepted.get("category") == candidate.get("category"):
                    accepted_tokens = set(accepted.get("title", "").lower().split())
                    max_len = max(len(candidate_tokens), len(accepted_tokens), 1)
                    similarity = len(candidate_tokens & accepted_tokens) / max_len

                    if similarity >= 0.50:
                        is_duplicate = True
                        logging.info("Duplicate filtered — retaining lower-cost entry.")
                        break

            if not is_duplicate:
                optimized_pool.append(candidate)

        with open(self.db_path, "w") as f:
            json.dump(optimized_pool, f, indent=4)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def orchestration_loop(self, search_matrix: list, operational_overhead: float):
        """Iterates over search terms, scrapes products, and writes good deals to disk."""
        for idx, search_token in enumerate(search_matrix, start=1):
            logging.info(f"Processing [{idx}/{len(search_matrix)}]: '{search_token}'")

            endpoints = self.discover_vendor_assets(search_token)
            endpoints.sort(key=lambda url: "amazon.com" not in url.lower())

            for endpoint in endpoints:
                try:
                    page_text = self.extract_clean_payload(endpoint)
                    if not page_text:
                        continue

                    metrics = self.analyze_payload_metrics(page_text)
                    if not metrics or not metrics.get("is_good_deal"):
                        continue

                    try:
                        scraped_cost = float(metrics.get("scraped_price", 0.0))
                        market_cost = float(metrics.get("regular_market_price", 0.0))
                    except (ValueError, TypeError):
                        continue

                    net_cost = scraped_cost + operational_overhead
                    retail_price = round(net_cost * (1 + self.profit_margin), 2)

                    record = {
                        "id": f"sys_gen_{int(datetime.now().timestamp())}_{os.urandom(2).hex()}",
                        "title": metrics.get("title", "Unknown"),
                        "price": retail_price,
                        "scraped_price": scraped_cost,
                        "regular_market_price": market_cost,
                        "category": metrics.get("genre", "Appliances"),
                        "condition": metrics.get("condition", "Unknown"),
                        "description": metrics.get("specifications", "N/A"),
                        "review_summary": metrics.get("review_summary", "N/A"),
                        "image_url": "https://images.example.com/placeholder.jpg",
                        "source_url": endpoint,
                        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }

                    self.execute_deduplication_sync(record)
                    time.sleep(random.uniform(5.5, 9.5))

                except Exception as e:
                    logging.error(f"Error processing endpoint '{endpoint}': {e}")
                    continue

            time.sleep(random.uniform(10.0, 18.0))


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

if __name__ == "__main__":
    pipeline = EnterprisePricingPipeline()

    # 4. EDIT THIS IF YOUR KEYWORDS FILE HAS A DIFFERENT NAME
    keywords_config = os.path.join(os.path.dirname(__file__), "keywords.txt")

    # 5. EDIT YOUR FLAT OVERHEAD FEE HERE ($5.00)
    overhead_fee = 5.00

    if os.path.exists(keywords_config):
        with open(keywords_config, "r") as f:
            inventory_grid = [line.strip() for line in f if line.strip()]
    else:
        logging.warning("keywords.txt not found. Using fallback search terms.")
        inventory_grid = ["gaming headset", "mini fridge", "office desk"]

    pipeline.orchestration_loop(inventory_grid, overhead_fee)

