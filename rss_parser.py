import os
import json
import re
import feedparser
from openai import OpenAI

# Configuration
RSS_URL = "https://rss.app/feeds/_91NiiDqi8o4EtTNB.xml"
DATA_FILE = "opportunities.json"
PROCESSED_LOG = "processed_guids.txt"

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def load_processed_guids():
    if os.path.exists(PROCESSED_LOG):
        with open(PROCESSED_LOG, "r") as f:
            return set(line.strip() for line in f)
    return set()

def save_processed_guid(guid):
    with open(PROCESSED_LOG, "a") as f:
        f.write(f"{guid}\n")

def load_existing_opportunities():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def clean_html_tags(text):
    """Removes standard web layout tags to deliver clean raw strings."""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text).strip()

def analyze_with_ai(description):
    prompt = f"""
    You are an expert career counselor. Decide if this item is highly relevant to job seekers, upskilling, or community support services.
    Description: {description}

    Rules:
    - Set 'is_relevant' to true ONLY for jobs, hiring events, training programs, or critical support services.
    - Choose exactly one: "Hiring Fair", "Training & Upskilling", "Networking Event", "Job Listing", "Support Services".

    Respond ONLY with a JSON object:
    {{
      "is_relevant": boolean,
      "category": "string"
    }}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"is_relevant": False, "category": None}

def main():
    print("Running synchronized layout pipeline...")
    processed_guids = load_processed_guids()
    existing_opportunities = load_existing_opportunities()
    
    feed = feedparser.parse(RSS_URL)
    new_entries_found = False
    
    for entry in reversed(feed.entries):
        guid = entry.get("id") or entry.get("link")
        if guid in processed_guids:
            continue
            
        summary_content = entry.get("summary", "") or entry.get("description", "")
        clean_description = clean_html_tags(summary_content)
        
        # Strip off messy cross-platform social text tags added by indexers
        clean_description = re.sub(r'^\[.*?\]', '', clean_description).strip()

        # Core Protection: Throw out empty posts immediately
        if not clean_description or len(clean_description) < 20:
            save_processed_guid(guid)
            continue

        # Look for images inside the post markup
        image_url = None
        img_match = re.search(r'<img[^>]+src="([^">]+)"', summary_content)
        if img_match:
            image_url = img_match.group(1)

        ai_decision = analyze_with_ai(clean_description)
        
        if ai_decision.get("is_relevant"):
            # This object format matches your original code keys perfectly
            new_opportunity = {
                "url": entry.get("link", ""),
                "image": image_url,
                "content_text": clean_description,
                "ai_category": ai_decision.get("category"),
                "date_published": entry.get("published", entry.get("updated", ""))
            }
            existing_opportunities.insert(0, new_opportunity)
            new_entries_found = True
            
        save_processed_guid(guid)
        processed_guids.add(guid)

    if new_entries_found:
        existing_opportunities = existing_opportunities[:100]
        with open(DATA_FILE, "w") as f:
            json.dump(existing_opportunities, f, indent=2)
    print("Pipeline synchronization complete.")

if __name__ == "__main__":
    main()
