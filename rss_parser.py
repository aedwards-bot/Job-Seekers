import os
import json
import re
import feedparser
from openai import OpenAI

# 1. Configuration (XML Fallback format)
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
    """Removes leftover HTML remnants from social descriptions."""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text).strip()

def analyze_with_ai(title, description):
    prompt = f"""
    You are an expert career counselor and economic development assistant. 
    Analyze this item and decide if it's highly relevant to job seekers, career changers, or those seeking upskilling or community support services.

    Title: {title}
    Description: {description}

    Rules:
    - Set 'is_relevant' to true ONLY if it's a job listing, training/certification program, hiring fair, resume workshop, networking event, or support services (like childcare, housing, utility/financial assistance).
    - Select exactly one 'category' from: "Hiring Fair", "Training & Upskilling", "Networking Event", "Job Listing", "Support Services".

    Respond ONLY with a JSON object matching this schema:
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
        print(f"AI Analysis failed: {e}")
        return {"is_relevant": False, "category": None}

def main():
    print("Starting optimized social feed parser...")
    processed_guids = load_processed_guids()
    existing_opportunities = load_existing_opportunities()
    
    feed = feedparser.parse(RSS_URL)
    new_entries_found = False
    
    for entry in reversed(feed.entries):
        guid = entry.get("id") or entry.get("link")
        if guid in processed_guids:
            continue
            
        raw_title = entry.get("title", "")
        # Handle cases where social feeds have no functional titles
        if "posted on" in raw_title.lower() or len(raw_title) > 120:
            title = ""
        else:
            title = raw_title

        summary_content = entry.get("summary", "") or entry.get("description", "")
        
        # Smart Image Extractor: Pull embedded graphics out of social media text markup
        image_url = None
        img_match = re.search(r'<img[^>]+src="([^">]+)"', summary_content)
        if img_match:
            image_url = img_match.group(1)
        elif "links" in entry:
            for l in entry.links:
                if "image" in l.get("type", ""):
                    image_url = l.get("href")
                    break

        clean_description = clean_html_tags(summary_content)
        # Strip generic systemic headers added by aggregators
        clean_description = re.sub(r'^\[.*?\]', '', clean_description).strip()

        ai_decision = analyze_with_ai(title, clean_description)
        
        if ai_decision.get("is_relevant"):
            print(f"  --> 🎉 Approved: [{ai_decision['category']}] -> {title[:40]}")
            
            new_opportunity = {
                "title": title,
                "url": entry.get("link", ""),
                "image": image_url,
                "content_text": clean_description,
                "ai_category": ai_decision.get("category"),
                "date_published": entry.get("published", entry.get("updated", "")),
                "original_source": "Job & Training Resources"
            }
            existing_opportunities.insert(0, new_opportunity)
            new_entries_found = True
            
        save_processed_guid(guid)
        processed_guids.add(guid)

    if new_entries_found:
        existing_opportunities = existing_opportunities[:100]
        with open(DATA_FILE, "w") as f:
            json.dump(existing_opportunities, f, indent=2)
        print("Opportunities data synchronized.")
    else:
        print("No new updates found.")

if __name__ == "__main__":
    main()
