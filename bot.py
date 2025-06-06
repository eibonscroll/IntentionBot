import requests
import os
import csv
from datetime import datetime, timezone
from better_profanity import profanity
from openai import OpenAI

# Load environment variables
try:
    TWITTER_BEARER_TOKEN = os.environ["TWITTER_BEARER_TOKEN"]
    OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
    BOT_HANDLE = os.environ["BOT_HANDLE"]
except KeyError as e:
    print(f"Missing environment variable: {e}")
    exit(1)

# OpenAI setup
client = OpenAI(api_key=OPENAI_API_KEY)

# Volume-mapped paths
BASE_PATH = "/mnt/data"
REPLIES_LOG = os.path.join(BASE_PATH, "replies_log.csv")
REJECTED_LOG = os.path.join(BASE_PATH, "rejected_log.csv")
BLOCKED_USERS_FILE = os.path.join(BASE_PATH, "blocked_users.txt")
LAST_ID_FILE = os.path.join(BASE_PATH, "last_seen_id.txt")
MAX_REPLIES = 3

SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
POST_URL = "https://api.twitter.com/2/tweets"

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

def load_blocked_users():
    if not os.path.exists(BLOCKED_USERS_FILE):
        return set()
    with open(BLOCKED_USERS_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())

def is_clean(text):
    if profanity.contains_profanity(text):
        return False
    if len(text.strip()) < 5:
        return False
    hate_keywords = ["kill", "nazi", "bomb", "rape", "suicide", "die", "genocide", "shoot", "torture"]
    return not any(word in text.lower() for word in hate_keywords)

def generate_reply(user_text):
    prompt = (
        "You are a spiritual guide. When someone asks a question, you reply with a short, "
        "emotionally supportive intention or affirmation they can repeat. It must be under 280 characters.\n"
        "Use one of these formats: 'Repeat after me: ...', 'Say this: ...', or 'Affirmation: ...'\n\n"
        f"Tweet: \"{user_text}\"\nReply:"
    )
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("OpenAI error:", e)
        return "I am temporarily unavailable. Please try again later."

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

    print("Requesting mentions from Twitter...")
    response = requests.get(SEARCH_URL, auth=bearer_oauth, params=params)
    if response.status_code == 429:
        print("Rate limit hit. Exiting.")
        return []
    elif response.status_code != 200:
        print(f"Twitter API error {response.status_code}: {response.text}")
        return []

    print("Rate limit remaining:", response.headers.get("x-rate-limit-remaining"))
    tweets = response.json().get("data", [])
    if tweets:
        most_recent_id = max(tweet["id"] for tweet in tweets)
        save_last_seen_id(most_recent_id)
    return tweets

def reply_to_tweet(tweet_id, message):
    payload = {
        "text": message,
        "reply": {"in_reply_to_tweet_id": tweet_id}
    }
    headers = {
        "Authorization": f"Bearer {TWITTER_BEARER_TOKEN}",
        "Content-Type": "application/json"
    }
    response = requests.post(POST_URL, json=payload, headers=headers)
    return response.status_code == 201, response.status_code, response.text

def write_csv_header_if_needed(filename, header):
    if not os.path.exists(filename):
        with open(filename, "w", newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)

def log_reply(tweet_id, user, text, reply):
    write_csv_header_if_needed(REPLIES_LOG, ["tweet_id", "user", "timestamp", "text", "reply"])
    with open(REPLIES_LOG, "a", newline='') as log:
        writer = csv.writer(log)
        writer.writerow([tweet_id, user, datetime.now(timezone.utc), text, reply])

def log_rejection(tweet_id, user, text, reason):
    write_csv_header_if_needed(REJECTED_LOG, ["tweet_id", "user", "timestamp", "reason", "text"])
    with open(REJECTED_LOG, "a", newline='') as rej:
        writer = csv.writer(rej)
        writer.writerow([tweet_id, user, datetime.now(timezone.utc), reason, text])
    with open(BLOCKED_USERS_FILE, "a") as blk:
        blk.write(f"{user}\n")

def respond_to_mentions():
    blocked_users = load_blocked_users()
    tweets = fetch_mentions()
    print(f"Mentions found: {len(tweets)}")

    for tweet in tweets[:MAX_REPLIES]:
        tweet_id = tweet["id"]
        text = tweet["text"]
        user = tweet["author_id"]

        if user in blocked_users:
            print(f"User {user} is blocked. Skipping.")
            continue

        print(f"Processing tweet from {user}: {text}")

        if not is_clean(text):
            print("Skipped due to content filtering.")
            log_rejection(tweet_id, user, text, "Filtered")
            continue

        reply = generate_reply(text)
        full_reply = f"@{BOT_HANDLE} {reply}"
        if len(full_reply) > 280:
            print("Reply too long. Skipping.")
            log_rejection(tweet_id, user, text, "Reply too long")
            continue

        success, status_code, response_text = reply_to_tweet(tweet_id, full_reply)
        if success:
            print("Replied.")
            log_reply(tweet_id, user, text, reply)
        else:
            print(f"Reply failed: {status_code} - {response_text}")

if __name__ == "__main__":
    print("Starting bot run at", datetime.now(timezone.utc))
    respond_to_mentions()
    print("Bot finished.")
