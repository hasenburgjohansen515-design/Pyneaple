import os
import json
import time
import random
import logging
import re
import socket
import atexit
from datetime import datetime
from urllib.parse import urlparse, quote_plus, parse_qs
from DrissionPage import ChromiumPage, ChromiumOptions
from filelock import FileLock
import concurrent.futures

# Swapped ollama for groq
from groq import Groq

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


class EnterprisePricingPipeline:

    def __init__(self):
        self.db_path = "../list/products.json"
        self.profit_margin = 0.20
        self.allowed_domains = ["amazon.com", "aliexpress.com", "temu.com"]

        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        ]

        # Initialize Groq Client. It automatically looks for the GROQ_API_KEY environment variable.
        self.groq_client = Groq()

        self._browser = None

        # Pre-compile all regex patterns once at init time.
        self._re_whitespace   = re.compile(r'\s+')
        self._re_json_block   = re.compile(r'(\{.*\})', re.DOTALL)
        self._re_float_finder = re.compile(r"\d+(\.\d+)?")
        self._re_nav_strip = re.compile(
            r'(skip to|cookie|privacy policy|terms of use|all rights reserved'
            r'|copyright ©|sign in|create account|your account|cart|wish list'
            r'|browse categories|department|back to top|follow us|newsletter'
            r'|download app|©\s*\d{4})',
            re.IGNORECASE
        )
        self._re_noise_line = re.compile(r'^(\W{0,3}|\d+(\.\d+)?|.{1,3})$')
        self._re_amazon_ad_host = re.compile(
            r'aax[-\w]*\.amazon\.com|amazon\.com/[^/]+/[^/]+/[^/]+/[^d][^p]',
            re.IGNORECASE
        )
        self._re_amazon_asin = re.compile(r'(https?://(?:www\.)?amazon\.com/[^?#]*/dp/[A-Z0-9]{10})')
        self._re_aliexpress_item = re.compile(r'(https?://(?:www\.)?aliexpress\.com/item/\d+\.html)')
        self._re_temu_product = re.compile(r'(https?://(?:www\.)?temu\.com/[^?#]+)')

    # ------------------------------------------------------------------
    # Browser management — single-process, single-browser model
    # ------------------------------------------------------------------

    def _find_free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return s.getsockname()[1]

    def _get_browser(self) -> ChromiumPage:
        if self._browser is None:
            co = ChromiumOptions()
            free_port = self._find_free_port()
            co.set_local_port(free_port)

            browser_path = "/usr/bin/google-chrome"
            if not os.path.exists(browser_path):
                browser_path = "/usr/bin/chromium"
            if os.path.exists(browser_path):
                co.set_browser_path(browser_path)

            profile_dir = "/tmp/drission_pipeline_profile"
            os.makedirs(profile_dir, exist_ok=True)
            co.set_user_data_path(profile_dir)

            co.headless(True)
            co.set_argument("--no-sandbox")
            co.set_argument("--disable-gpu")
            co.set_argument("--disable-dev-shm-usage")
            co.set_user_agent(random.choice(self.user_agents))

            self._browser = ChromiumPage(addr_or_opts=co)
            atexit.register(self.close_pipeline_assets)
            logging.info("Browser instance started.")

        return self._browser

    def close_pipeline_assets(self):
        if self._browser:
            try:
                self._browser.quit()
                logging.info("Browser shut down cleanly.")
            except Exception as e:
                logging.error(f"Error during browser teardown: {e}")
            finally:
                self._browser = None

    # ------------------------------------------------------------------
    # Tab-based screxport GROQ_API_KEY="gsk_yOuRaCtUaLkEyHeRe..."ng — one tab per URL, safe for ThreadPoolExecutor
    # ------------------------------------------------------------------

    def _scrape_in_new_tab(self, url: str) -> dict | None:
        if not self.verify_domain_compliance(url):
            return None

        tab = None
        try:
            browser = self._get_browser()
            tab = browser.new_tab()
            tab.get(url)
            time.sleep(random.uniform(2.0, 3.5))

            body_element = tab.ele("tag:body")
            page_text = body_element.text if body_element else ""
            page_text = self._re_whitespace.sub(' ', page_text).strip()

            img_element = (
                tab.ele("tag:img@@id=landingImage") or
                tab.ele("tag:img@@class*=-main-img") or
                tab.ele("tag:img@@src*=/item/") or
                tab.ele("tag:img@@class*=product-image")
            )
            image_url = img_element.attr("src") if img_element else "https://images.example.com/placeholder.jpg"

            return {"text": page_text, "image_url": image_url}

        except Exception as e:
            logging.error(f"Failed to scrape {url}: {e}")
            return None
        finally:
            if tab:
                try:
                    tab.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # URL / query utilities
    # ------------------------------------------------------------------

    def verify_domain_compliance(self, url: str) -> bool:
        try:
            parsed = urlparse(url.lower())
            netloc = parsed.netloc.lstrip("www.")
            for domain in self.allowed_domains:
                if netloc == domain or netloc.endswith("." + domain):
                    if domain == "amazon.com" and netloc not in ("amazon.com", "www.amazon.com"):
                        return False
                    return True
            return False
        except Exception:
            return False

    def _canonicalize_url(self, url: str) -> str | None:
        m = self._re_amazon_asin.search(url)
        if m:
            return m.group(1)
        m = self._re_aliexpress_item.search(url)
        if m:
            return m.group(1)
        m = self._re_temu_product.search(url)
        if m:
            return m.group(1)
        return None

    def sanitize_and_tokenize_query(self, raw_query: str) -> str:
        tokens = [
            t.strip()
            for t in re.split(r"[-_,\s\.\/\\]+", raw_query)
            if t.strip()
        ]
        return " ".join(tokens)

    # ------------------------------------------------------------------
    # Signal Noise reduction
    # ------------------------------------------------------------------

    def _extract_product_signals(self, raw_text: str, max_chars: int = 2000) -> str:
        lines = raw_text.splitlines()
        scored = []

        for line in lines:
            line = line.strip()
            if not line:
                continue
            if self._re_nav_strip.search(line):
                continue
            if self._re_noise_line.match(line):
                continue

            score = 0
            if re.search(r'[\$\£\€]\s*\d+[\.,]\d{2}', line):
                score += 10
            elif re.search(r'\d+\.\d{2}', line):
                score += 6
            if len(line) > 30 and line[0].isupper():
                score += 4
            if ':' in line and len(line) < 120:
                score += 3
            if re.search(r'(star|rating|review|out of 5|\d\.\d/5)', line, re.IGNORECASE):
                score += 5
            if re.search(r'(new|used|refurbished|in stock|ships from|sold by)', line, re.IGNORECASE):
                score += 4
            if len(line) > 60:
                score += 2
            if score > 0:
                scored.append((score, line))

        scored.sort(key=lambda x: x[0], reverse=True)
        result_lines = []
        total = 0
        for _, line in scored:
            if total + len(line) > max_chars:
                break
            result_lines.append(line)
            total += len(line)

        return "\n".join(result_lines)

    # ------------------------------------------------------------------
    # Discovery & harvesting
    # ------------------------------------------------------------------

    def _harvest_links_from_current_page(self, browser_or_tab, payload_depth: int) -> list:
        found = []
        for anchor in browser_or_tab.eles("t:a"):
            raw_href = anchor.attr("href")
            if not raw_href:
                continue

            actual_url = raw_href
            if any(wrap in raw_href for wrap in ["/url?", "q=", "target=", "/l/?", "uddg="]):
                try:
                    parsed_query = urlparse(raw_href).query
                    query_params = parse_qs(parsed_query)
                    for key in ["q", "url", "target", "uddg", "udg"]:
                        if key in query_params:
                            actual_url = query_params[key][0]
                            break
                except Exception:
                    actual_url = raw_href

            if actual_url.startswith("//"):
                actual_url = "https:" + actual_url

            canonical = self._canonicalize_url(actual_url)
            if (
                canonical
                and self.verify_domain_compliance(canonical)
                and canonical not in found
            ):
                found.append(canonical)
                logging.info(f"Discovered valid link: {canonical}")
                if len(found) >= payload_depth:
                    break

        return found

    def _harvest_direct_site_links(self, browser_or_tab, patterns: list, limit: int) -> list:
        found = []
        for anchor in browser_or_tab.eles("t:a"):
            raw_href = anchor.attr("href")
            if not raw_href:
                continue

            if raw_href.startswith("//"):
                raw_href = "https:" + raw_href
            elif raw_href.startswith("/"):
                current = browser_or_tab.url or ""
                parsed_base = urlparse(current)
                raw_href = f"{parsed_base.scheme}://{parsed_base.netloc}{raw_href}"

            canonical = self._canonicalize_url(raw_href)
            if (
                canonical
                and self.verify_domain_compliance(canonical)
                and canonical not in found
                and any(p in canonical for p in patterns)
            ):
                found.append(canonical)
                logging.info(f"[Direct] Discovered: {canonical}")
                if len(found) >= limit:
                    break

        return found

    def discover_vendor_assets(self, market_query: str, payload_depth: int = 3) -> list:
        keywords = self.sanitize_and_tokenize_query(market_query)
        logging.info(f"Initiating asset discovery for: '{keywords}'")

        matched_endpoints = []
        encoded_kw = quote_plus(keywords)
        site_filter = quote_plus(f"(site:amazon.com OR site:aliexpress.com OR site:temu.com) {keywords}")

        search_sources = [
            {"name": "Google", "url": f"https://www.google.com/search?q={site_filter}", "block_signals": ["sorry", "captcha", "unusual traffic", "robot"], "is_direct": False},
            {"name": "DuckDuckGo", "url": f"https://html.duckduckgo.com/html/?q={site_filter}", "block_signals": [], "is_direct": False},
            {"name": "Bing", "url": f"https://www.bing.com/search?q={site_filter}", "block_signals": ["access denied", "captcha"], "is_direct": False},
            {"name": "Amazon Direct", "url": f"https://www.amazon.com/s?k={encoded_kw}", "block_signals": ["robot check", "enter the characters"], "is_direct": True, "product_url_patterns": ["/dp/"]},
            {"name": "AliExpress Direct", "url": f"https://www.aliexpress.com/wholesale?SearchText={encoded_kw}", "block_signals": [], "is_direct": True, "product_url_patterns": ["/item/"]},
        ]

        try:
            browser = self._get_browser()

            for source in search_sources:
                if len(matched_endpoints) >= payload_depth:
                    break

                remaining = payload_depth - len(matched_endpoints)
                logging.info(f"Trying search source: {source['name']} (need {remaining} more links)")

                try:
                    browser.get(source["url"])
                    if source["is_direct"]:
                        time.sleep(random.uniform(1.5, 2.5))
                    else:
                        time.sleep(random.uniform(2.5, 3.5))

                    page_title = browser.title.lower()
                    logging.info(f"[{source['name']}] Page title: '{page_title}'")

                    is_blocked = any(sig in page_title for sig in source["block_signals"])
                    is_url_title = page_title.startswith("http://") or page_title.startswith("https://")

                    if is_blocked or is_url_title:
                        logging.warning(f"[{source['name']}] Blocked or bare URL title. Skipping.")
                        continue

                    if source["is_direct"]:
                        patterns = source.get("product_url_patterns", ["/dp/", "/item/"])
                        new_links = self._harvest_direct_site_links(browser, patterns, remaining)
                    else:
                        new_links = self._harvest_links_from_current_page(browser, remaining)

                    for link in new_links:
                        if link not in matched_endpoints:
                            matched_endpoints.append(link)

                    logging.info(f"[{source['name']}] Collected {len(new_links)} links. Total: {len(matched_endpoints)}")

                except Exception as e:
                    logging.error(f"[{source['name']}] Source failed: {e}")
                    continue

        except Exception as e:
            logging.error(f"Discovery exception: {e}")

        return matched_endpoints

    # ------------------------------------------------------------------
    # CLOUD LLM INTEGRATION (GROQ — lightning fast & free)
    # ------------------------------------------------------------------

    def analyze_payload_metrics(self, page_text: str) -> dict | None:
        # Strict explicit schema configuration for Groq's JSON mode
        system_directive = (
            "You are a raw data extraction pipeline layer. Analyze the provided text and "
            "return ONLY a valid, minimized JSON object matching this schema blueprint perfectly.\n"
            "Do not output markdown triple backticks. Do not output conversational explanations.\n\n"
            "REQUIRED JSON SCHEMA:\n"
            "{\n"
            '  "title": "String product name",\n'
            '  "scraped_price": Float,\n'
            '  "regular_market_price": Float,\n'
            '  "genre": "Furniture" or "Consoles" or "Appliances",\n'
            '  "condition": "String state description",\n'
            '  "specifications": "String specs details",\n'
            '  "review_summary": "String analysis",\n'
            '  "is_good_deal": Boolean\n'
            "}"
        )

        try:
            # Updated to the current active free-tier model
            response = self.groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": system_directive},
                    {"role": "user", "content": f"Extract data from:\n\n{page_text}"}
                ],
                # Mandates JSON formatting directly from the endpoint engine
                response_format={"type": "json_object"},
                temperature=0.1
            )

            raw = response.choices[0].message.content
            if not raw:
                return None

            clean = raw.strip()
            parsed = json.loads(clean)

            # Cleanup price string structural variance if any crept through
            for key in ("scraped_price", "regular_market_price"):
                if key in parsed and isinstance(parsed[key], str):
                    match = self._re_float_finder.search(parsed[key])
                    parsed[key] = float(match.group()) if match else 0.0

            return parsed

        except Exception as e:
            logging.error(f"Failed Groq inference or JSON mapping: {e}")
            return None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def execute_deduplication_sync(self, proposed_record: dict):
        lock_path = self.db_path + ".lock"
        lock = FileLock(lock_path)

        with lock:
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
            dataset.sort(key=lambda x: float(x.get("scraped_price", float("inf"))))

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
    # Workers & Orchestration
    # ------------------------------------------------------------------

    def process_single_endpoint(self, endpoint: str, operational_overhead: float):
        try:
            payload_data = self._scrape_in_new_tab(endpoint)
            if not payload_data:
                return

            page_text = payload_data.get("text", "")
            discovered_img = payload_data.get("image_url", "https://images.example.com/placeholder.jpg")

            if not page_text:
                return

            filtered_text = self._extract_product_signals(page_text)
            logging.info(
                f"Text reduced: {len(page_text)} → {len(filtered_text)} chars "
                f"({100 - round(len(filtered_text)/max(len(page_text),1)*100)}% noise stripped)"
            )

            if not filtered_text:
                logging.warning("Signal extraction returned empty — falling back to raw truncation.")
                filtered_text = page_text[:3000]

            metrics = self.analyze_payload_metrics(filtered_text)
            if not metrics or not metrics.get("is_good_deal"):
                return

            try:
                scraped_cost = float(metrics.get("scraped_price", 0.0))
                market_cost = float(metrics.get("regular_market_price", 0.0))
            except (ValueError, TypeError):
                return

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
                "image_url": discovered_img,
                "source_url": endpoint,
                "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            self.execute_deduplication_sync(record)
            logging.info(f"Record synchronized: {record['title']}")
            time.sleep(random.uniform(2.0, 4.0))

        except Exception as e:
            logging.error(f"Operational failure for '{endpoint}': {e}")

    def orchestration_loop(self, search_matrix: list, operational_overhead: float):
        logging.info(f"Starting pipeline. Keywords to process: {len(search_matrix)}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            for idx, search_token in enumerate(search_matrix, start=1):
                logging.info(f"--- Keyword [{idx}/{len(search_matrix)}]: '{search_token}' ---")

                endpoints = self.discover_vendor_assets(search_token)
                endpoints = list(set(endpoints))

                if not endpoints:
                    logging.info(f"No valid vendor links for '{search_token}'. Moving on.")
                    continue

                logging.info(f"Found {len(endpoints)} links. Launching parallel extraction...")

                future_to_url = {
                    executor.submit(self.process_single_endpoint, url, operational_overhead): url
                    for url in endpoints
                }

                for future in concurrent.futures.as_completed(future_to_url):
                    url = future_to_url[future]
                    try:
                        future.result()
                    except Exception as e:
                        logging.error(f"Thread execution failed for {url}: {e}")


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

if __name__ == "__main__":
    pipeline = EnterprisePricingPipeline()
    keywords_config = os.path.join(os.path.dirname(__file__), "keywords.txt")
    overhead_fee = 5.00

    if os.path.exists(keywords_config):
        with open(keywords_config, "r") as f:
            inventory_grid = [line.strip() for line in f if line.strip()]
    else:
        logging.warning("keywords.txt not found. Using fallback search terms.")
        inventory_grid = ["gaming headset", "mini fridge", "office desk"]

    pipeline.orchestration_loop(inventory_grid, overhead_fee)