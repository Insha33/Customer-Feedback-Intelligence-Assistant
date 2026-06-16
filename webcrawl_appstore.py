import requests
import json
from dotenv import load_dotenv
import os
import sys

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def classify_review(review_text):

    prompt = f"""
    Analyze the Instagram Play Store review.

    Return ONLY valid JSON.

    Choose exactly ONE category using these meanings:
    - Authentication Issues: Login, signup, password reset, two-factor authentication, verification codes, session expiry, hacked-account recovery, or being unable to access an account because authentication is failing.
    - Account Suspension: Disabled, banned, suspended, restricted, locked, removed, or deactivated accounts; appeals; account status warnings; suspected policy violations causing loss of account access.
    - Performance Issues: App crashes, freezes, slow loading, lag, battery drain, overheating, upload/download failures, blank screens, update bugs, broken notifications, or other technical reliability problems.
    - Messaging & DMs: Direct messages, message requests, group chats, disappearing messages, media sharing in chat, inbox behavior, message delivery, calling from chat, or unwanted contact through DMs.
    - Reels & Feed Algorithm: Reels, feed ranking, recommendations, suggested posts, Explore content, algorithm quality, repetitive content, irrelevant posts, reach/discovery in the feed, or short-video viewing experience.
    - Privacy Concerns: Private account controls, data use, tracking, visibility of posts/stories/activity, location sharing, contacts sync, blocked/restricted users, message privacy, or who can see/contact the user.
    - Content Moderation: Removal, flagging, reporting, appeals, community guidelines, hate/harassment/spam/graphic content enforcement, or complaints that unsafe content is allowed or normal content is taken down.
    - Feature Requests: Requests for new features, restoring old features, UI changes, customization, missing options, or product improvements that are not primarily bug reports.
    - Customer Support: Help center, support tickets, response delays, inability to contact support, poor support experience, unresolved reports, or frustration with getting human/helpful assistance.
    - Positive Experience: Praise, satisfaction, enjoyment, appreciation, love for the app, successful experiences, or compliments where no clear problem/request dominates.
    - Creator Tools: Professional dashboard, insights/analytics, creator/business accounts, monetization, branded content, post/reel editing tools, scheduling, audience growth tools, or creator workflow problems.
    - General Feedback: Broad opinions, unclear complaints, vague rants, mixed comments without a dominant category, or feedback that does not fit the other categories.

    Classification rules:
    - Pick the most specific category that matches the main issue in the review.
    - If a review mentions multiple issues, choose the one the user emphasizes most.
    - Use Positive Experience only when the review is mainly praise.
    - Use General Feedback only when no specific category clearly applies.

    Sentiment:
    - positive
    - neutral
    - negative

    Review:
    {review_text}

    JSON format:
    {{
        "category": "...",
        "sentiment": "..."
    }}
    """

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "openai/gpt-4.1-mini",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
    )

    result = response.json()

    content = result["choices"][0]["message"]["content"]

    return json.loads(content)


if __name__ == "__main__":
    review_text = "Instagram is shit muhuahahahaha i dont like the new instant feature"
    classification = classify_review(review_text)
    print(json.dumps(classification, indent=2))
