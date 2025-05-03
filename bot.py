import tweepy
import openai
import time
import os

from config import (
    TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN,
    TWITTER_ACCESS_SECRET, OPENAI_API_KEY
)

# Authenticate Twitter
auth = tweepy.OAuth1UserHandler(
    TWITTER_API_KEY, TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
)
api = tweepy.API(auth)

# Set OpenAI key
openai.api_key = OPENAI_API_KEY

LAST_ID_FILE = "last_mention_id.txt"

def load_last_seen_id():
    if os.path.exists(LAST_ID_FILE):
        with open(LAST_ID_FILE, "r") as f:
            return int(f.read().strip())
    return None

def save_last_seen_id(tweet_id):
    with open(LAST_ID_FILE, "w") as f:
        f.write(str(tweet_id))

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

def respond_to_mentions():
    print("🔄 Checking for new mentions...")
    last_id = load_last_seen_id()
    mentions = api.mentions_timeline(since_id=last_id, tweet_mode='extended')

    for mention in reversed(mentions):
        print(f"💬 @{mention.user.screen_name}: {mention.full_text}")
        reply = generate_reply(mention.full_text)
        reply_text = f"@{mention.user.screen_name} {reply}"

        if len(reply_text) <= 280:
            api.update_status(status=reply_text, in_reply_to_status_id=mention.id)
            print("✅ Replied:", reply_text)
            save_last_seen_id(mention.id)
        else:
            print("⚠️ Reply too long, skipping.")

if __name__ == "__main__":
    while True:
        try:
            respond_to_mentions()
            time.sleep(90)  # Adjust for polling interval
        except Exception as e:
            print("❌ Error:", e)
            time.sleep(120)
