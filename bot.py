import requests
import openai
import os
import time
from better_profanity import profanity

# Load environment variables
TWITTER_BEARER_TOKEN = os.environ["TWITTER_BEARER_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
BOT_HANDLE = os.environ["BOT_HANDLE"]

openai.api_key = OPENAI_API_KEY

SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
POST_URL = "https://api.twitter.com/2/tweets"
LAST_ID_FILE = "last_seen_id.txt"

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
    prompt = (
        "You are a spiritual guide. When someone asks a question, you reply with a short, "
        "emotionally supportive intention or affirmation they can repeat. It must be under 280 characters.\n"
        "Use one of these formats: 'Repeat after me: ...', 'Say this: ...', or 'Affirmation: ...'\n\n"
        f"Tweet: \"{user_text}\"\nReply:"
    )
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

    print("⏳ Making Twitter request...")
    response = requests.get(SEARCH_URL, auth=bearer_oauth, params=params)
    print(f"Status: {response.status_code}")

    if response.status_code == 429:
        print("Rate limit hit. Sleeping 15 mins...")
        time.sleep(900)
        return []

    if response.status_code != 200:
        print(f"Twitter API Error {response.status_code}: {response.text}")
        return []

    data = response.json().get("data", [])
    if data:
        most_recent_id = max(tweet["id"] for tweet in data)
        save_last_seen_id(most_recent_id)
    return data

def reply_to_tweet(tweet_id, message):
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
    response = requests.post(POST_URL, json=payload, headers=headers)
    if response.status_code == 201:
        print(f"Replied: {message}")
    else:
        print(f"Reply failed: {response.status_code} - {response.text}")

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

        reply_to_tweet(tweet_id, reply_text)

if __name__ == "__main__":
    while True:
        try:
            respond_to_mentions()
            time.sleep(900)  # Every 15 minutes
        except Exception as e:
            print("Error:", e)
            time.sleep(900)
