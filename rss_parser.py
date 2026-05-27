import os
import json
import feedparser
from openai import OpenAI

# 1. Configuration
RSS_URL = "https://rss.app/feeds/v1.1/_91NiiDqi8o4EtTNB.json"
DATA_FILE = "opportunities.json"
PROCESSED_LOG = "processed_guids.txt"

# Initialize OpenAI Client (Make sure OPENAI_API_KEY is set in your environment)
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

def analyze_with_ai(title, description):
    """Sends the post to OpenAI to filter and classify."""
    prompt = f"""
    You are an expert career counselor and economic development assistant. 
    Analyze this item and decide if it's highly relevant to job seekers, career changers, or those seeking upskilling or social service supports.

    Title: {title}
    Description: {description}

    Rules:
    - Set 'is_relevant' to true ONLY if it's a job listing, training/certification program, hiring fair, resume workshop, networking event, or support services (like childcare, housing, financial support, etc).
    - Select exactly one 'category' from: "Hiring Fair", "Training & Upskilling", "Networking Event", "Job Listing", and "Support Services".

    Respond ONLY with a JSON object matching this schema:
    {{
      "is_relevant": boolean,
      "category": "string"
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Highly cost-effective and accurate for classification
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        print(f"AI Analysis failed: {e}")
        return {"is_relevant": False, "category": None}

def main():
    print("Starting RSS processing pipeline...")
    
    processed_guids = load_processed_guids()
    existing_opportunities = load_existing_opportunities()
    
    # Fetch and parse the feed
    feed = feedparser.parse(RSS_URL)
    new_entries_found = False
    
    # Process items from oldest to newest
    for entry in reversed(feed.entries):
        guid = entry.get("id") or entry.get("link")
        
        # Skip if we've already processed this item in a previous run
        if guid in processed_guids:
            continue
            
        print(f"Processing new item: {entry.title}")
        
        title = entry.get("title", "")
        description = entry.get("summary", "") or entry.get("description", "")
        link = entry.get("link", "")
        pub_date = entry.get("published", "")
        
        # Extract image if available in feed tags
        image_url = None
        if "links" in entry:
            for l in entry.links:
                if "image" in l.get("type", ""):
                    image_url = l.get("href")
                    break

        # Let the AI judge and tag the content
        ai_decision = analyze_with_ai(title, description)
        
        if ai_decision.get("is_relevant"):
            print(f"  --> 🎉 AI Flagged as RELEVANT: Tagged as [{ai_decision['category']}]")
            
            # Format to match the frontend expectations perfectly
            new_opportunity = {
                "title": title,
                "url": link,
                "image": image_url,
                "content_text": description,
                "ai_category": ai_decision.get("category"),
                "date_published": pub_date,
                "original_source": feed.feed.get("title", "City Feed")
            }
            
            # Prepend to the top of our list so newest items show first
            existing_opportunities.insert(0, new_opportunity)
            new_entries_found = True
        else:
            print("  --> ❌ AI Flagged as IRRELEVANT. Skipping.")
            
        # Log the GUID so we never spend tokens analyzing it again
        save_processed_guid(guid)
        processed_guids.add(guid)

    # If we found new relevant items, update the website's JSON file
    if new_entries_found:
        # Keep the total file size reasonable (e.g., store only the latest 100 opportunities)
        existing_opportunities = existing_opportunities[:100]
        
        with open(DATA_FILE, "w") as f:
            json.dump(existing_opportunities, f, indent=2)
        print(f"Updated {DATA_FILE} successfully.")
    else:
        print("No new relevant opportunities found in this run.")

if __name__ == "__main__":
    main()
