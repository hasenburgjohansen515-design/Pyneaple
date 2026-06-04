import os
import json
from datetime import datetime
from urllib.parse import urlparse
from DrissionPage import ChromiumPage
import requests

# Path configuration
JSON_DB_PATH = "../list/products.json"
DEFAULT_PROFIT_MARGIN = 0.20  

# OpenRouter Configuration
OPENROUTER_API_KEY = "your_openrouter_api_key_here" # Paste your key here
MODEL_NAME = "meta-llama/llama-3-8b-instruct:free" 

# Approved retail domains
ALLOWED_DOMAINS = ["amazon.com", "aliexpress.com", "temu.com"]

def is_url_allowed(url):
    """Checks if the URL belongs to Amazon, AliExpress, or Temu."""
    parsed_url = urlparse(url.lower())
    domain = parsed_url.netloc
    
    # Remove 'www.' if present to standardize checking
    if domain.startswith("www."):
        domain = domain[4:]
        
    for allowed in ALLOWED_DOMAINS:
        if allowed in domain:
            return True
    return False

def fetch_dynamic_page(url):
    """Launches DrissionPage, waits for JS execution, and grabs visible text."""
    if not is_url_allowed(url):
        print(f"Target Rejected: URL is not from Amazon, AliExpress, or Temu.")
        return None

    print(f"Opening browser to scrape approved domain: {url}")
    page = ChromiumPage()
    try:
        page.get(url)
        return page.text 
    except Exception as e:
        print(f"Browser extraction error: {e}")
        return None
    finally:
        page.quit()

def query_open_source_llm(page_text):
    """Sends page data to an open-source LLM and demands a clean JSON schema back."""
    print("Sending text data to LLM for classification and extraction...")
    
    system_instruction = (
        "You are a strict data extraction engine. Analyze the product text provided by the user. "
        "Your response must be a single, valid JSON object matching this exact structural format. "
        "Do not include any pleasantries, markdown blocks like ```json, or conversational text.\n\n"
        "EXPECTED JSON FORMAT:\n"
        "{\n"
        '  "title": "Main commercial name of item",\n'
        '  "scraped_price": 0.00, \n'
        '  "regular_market_price": 0.00, \n'
        '  "genre": "Must be exactly: Furniture, Consoles, or Appliances",\n'
        '  "condition": "Physical condition (e.g., New, Used). If missing use \'Unknown\'",\n'
        '  "specifications": "Concise bulleted summary of specifications or dimensions",\n'
        '  "review_summary": "Short summary of ratings/reviews. If missing use \'No reviews found\'",\n'
        '  "is_good_deal": true\n'
        "}\n\n"
        "Rule: Set 'is_good_deal' to true only if scraped_price is lower than regular_market_price."
    )

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": f"Extract data from this website text:\n\n{page_text}"}
        ],
        "response_format": {"type": "json_object"} 
    }

    try:
        response = requests.post(
            "[https://openrouter.ai/api/v1/chat/completions](https://openrouter.ai/api/v1/chat/completions)",
            headers=headers,
            json=payload,
            timeout=15
        )
        result = response.json()
        raw_json_string = result['choices'][0]['message']['content']
        return json.loads(raw_json_string)
    except Exception as e:
        print(f"LLM Processing Error: {e}")
        return None

def calculate_final_listing_price(scraped_price, shipping_cost):
    base_cost = scraped_price + shipping_cost
    final_price = base_cost * (1 + DEFAULT_PROFIT_MARGIN)
    return round(final_price, 2)

def clean_title(title):
    """Helper to break title into words for basic similarity matching."""
    return set(title.lower().replace("-", " ").replace(",", " ").split())

def process_and_save_smart_deal(new_product):
    """
    Scans products.json. If a matching product exists and the new one is cheaper,
    it deletes the old item and replaces it with the cheaper listing.
    """
    os.makedirs(os.path.dirname(JSON_DB_PATH), exist_ok=True)
    
    if not os.path.exists(JSON_DB_PATH):
        with open(JSON_DB_PATH, "w") as f:
            json.dump([], f)

    with open(JSON_DB_PATH, "r") as f:
        try:
            database = json.load(f)
        except json.JSONDecodeError:
            database = []

    duplicate_found = False
    replace_index = -1
    new_words = clean_title(new_product["title"])

    for index, old_product in enumerate(database):
        # Match only items within the exact same category
        if old_product["category"] == new_product["category"]:
            old_words = clean_title(old_product["title"])
            
            # Look for overlapping keywords to catch alternate model configurations
            shared_words = new_words.intersection(old_words)
            
            # If titles share 50% or more common keywords, consider it a match
            if len(shared_words) / max(len(new_words), len(old_words)) >= 0.5:
                duplicate_found = True
                
                # Check if the newly scraped alternative is more affordable
                if new_product["scraped_price"] < old_product["scraped_price"]:
                    print(f" Better Value Discovered! Replacing '{old_product['title']}' (${old_product['price']}) with cheaper source item: '{new_product['title']}' (${new_product['price']}).")
                    replace_index = index
                else:
                    print(f" Match found, but current item listed (${old_product['price']}) is already cheaper than this alternative. Skipping.")
                break

    if duplicate_found:
        if replace_index != -1:
            # Drop the pricier duplicate entry out of the list completely
            database.pop(replace_index)
            # Inject the optimized, cheaper entry
            database.append(new_product)
    else:
        # Brand new unique item configuration, append cleanly
        print(f"New item configuration unique identifier logged.")
        database.append(new_product)

    # Save modifications back to the JSON file
    if not duplicate_found or (duplicate_found and replace_index != -1):
        with open(JSON_DB_PATH, "w") as f:
            json.dump(database, f, indent=4)
        print(f"Layout Updated! Successfully logged '{new_product['title']}' into products.json.")

def run_scraper_pipeline(target_url, estimated_shipping):
    print("\n--- Starting Active Production Scraper ---")
    
    # 1. Fetch dynamic page text (and check allowed retail platforms)
    page_text = fetch_dynamic_page(target_url)
    if not page_text: return

    # 2. Extract Data via OpenRouter LLM
    ai_data = query_open_source_llm(page_text)
    if not ai_data: return

    # 3. Deal Filter Guardrail
    if not ai_data.get("is_good_deal"):
        print(f"Item Filtered out: '{ai_data.get('title')}' is not a discount price deal.")
        return

    # 4. Math Calculations Engine
    selling_price = calculate_final_listing_price(float(ai_data["scraped_price"]), estimated_shipping)

    # 5. Database Compilation Mapping
    final_product = {
        "id": f"scraped_{int(datetime.now().timestamp())}",
        "title": ai_data["title"],
        "price": selling_price,
        "scraped_price": float(ai_data["scraped_price"]),
        "regular_market_price": float(ai_data["regular_market_price"]),
        "category": ai_data["genre"],
        "condition": ai_data.get("condition", "Unknown"),
        "description": ai_data.get("specifications", "N/A"),
        "review_summary": ai_data.get("review_summary", "N/A"),
        "image_url": "[https://images.example.com/placeholder.jpg](https://images.example.com/placeholder.jpg)", 
        "source_url": target_url,
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    # 6. Run deduplication and save
    process_and_save_smart_deal(final_product)

if __name__ == "__main__":
    # Test your clean setup using an explicit domain link
    target_url = "[https://www.amazon.com/dp/B0EXAMPLE](https://www.amazon.com/dp/B0EXAMPLE)" 
    shipping_cost = 5.00
    
    run_scraper_pipeline(target_url, shipping_cost)