import requests
import openai
import os
import time
from better_profanity import profanity

# Load environment variables
TWITTER_BEARER_TOKEN = os.environ["TWITTER_BEARER_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
BOT_HANDLE = os.environ["BOT_HANDLE"]

# Set OpenAI key
openai.api_key = OPENAI_API_KEY

# Twitter search endpoint
SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
LAST_ID_FILE = "last_seen_id.txt"

# Load profanity filter
profanity.load_censor_words()

def bearer_oauth(r):
    r.headers["Authorization"] = f"Bearer {TWITTER_BEARER_TOKEN}"
    r.headers["User-Agent"] = "IntentionBot"
    return r

def load_last_seen_id():
    if os.path.exists(LAST_ID_FILE):
        with open(LAST_ID_FILE, "r") as f:
            return f.read().strip()
    return None

def save_last_seen_id(tweet_id):
    with open(LAST_ID_FILE, "w") as f:
        f.write(tweet_id)

def is_clean(text):
    if profanity.contains_profanity(text):
        return False
    if len(text.strip()) < 5:
        return False
    hate_keywords = [
        "kill", "nazi", "gas", "bomb", "rape", "suicide", "die",
        "genocide", "shoot", "massacre", "torture", "lynch"
    ]
    return not any(word in text.lower() for word in hate_keywords)

def generate_reply(user_text):
    prompt = f"""You are a spiritual guide. When someone asks a question, you reply with a short, emotionally supportive intention or affirmation they can repeat.
It must be under 280 characters.
Use one of these formats: "Repeat after me: ...", "Say this: ...", or "Affirmation: ..."

Tweet: "{user_text}"
Reply:"""

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )

    return response['choices'][0]['message']['content'].strip()

def fetch_mentions():
    last_id = load_last_seen_id()
    query = f"@{BOT_HANDLE} -is:retweet"
    params = {
        "query": query,
        "tweet.fields": "author_id,conversation_id",
        "max_results": 10
    }
    if last_id:
        params["since_id"] = last_id

    response = requests.get(SEARCH_URL, auth=bearer_oauth, params=params)
    if response.status_code != 200:
        print(f"Twitter API Error {response.status_code}: {response.text}")
        return []

    data = response.json().get("data", [])
    if data:
        save_last_seen_id(data[0]["id"])
    return data

def reply_to_tweet(tweet_id, user_id, message):
    url = "https://api.twitter.com/2/tweets"
    payload = {
        "text": message,
        "reply": {
            "in_reply_to_tweet_id": tweet_id
        }
    }
    headers = {
        "Authorization": f"Bearer {TWITTER_BEARER_TOKEN}",
        "Content-Type": "application/json"
    }
    r = requests.post(url, json=payload, headers=headers)
    if r.status_code == 201:
        print(f"Replied: {message}")
    else:
        print(f"Reply failed: {r.status_code} - {r.text}")

def respond_to_mentions():
    print("Checking for new mentions...")
    tweets = fetch_mentions()

    for tweet in tweets:
        tweet_id = tweet["id"]
        text = tweet["text"]
        author_id = tweet["author_id"]

        print(f"@{author_id}: {text}")

        if not is_clean(text):
            print("Skipping due to profanity or spam.")
            continue

        reply = generate_reply(text)
        reply_text = f"@{BOT_HANDLE} {reply}"
        if len(reply_text) > 280:
            print("Reply too long, skipping.")
            continue

        reply_to_tweet(tweet_id, author_id, reply_text)

if __name__ == "__main__":
    while True:
        try:
            respond_to_mentions()
            time.sleep(300)  # Poll every 5 minutes
        except Exception as e:
            print("Error:", e)
            time.sleep(300)
