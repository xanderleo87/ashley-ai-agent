"""
Ashley Reasoning Engine - Email Intelligence Module.
Analyzes emails using OpenAI to categorize, detect spam/scams,
assess urgency, and generate actionable suggestions.
"""

import json
from openai import OpenAI
import config

client = OpenAI(api_key=config.OPENAI_API_KEY)


def analyze_email(sender_name: str, sender_email: str, subject: str, snippet: str) -> dict:
    """
    Analyze an incoming email and return structured intelligence.
    Returns: category, urgency, spam_score, suggestions, summary
    """
    prompt = f"""You are Ashley, an elite AI email analyst. Analyze this incoming email and return a JSON assessment.

EMAIL DATA:
- From: {sender_name} <{sender_email}>
- Subject: {subject}
- Preview: {snippet}

ANALYZE AND RETURN VALID JSON WITH THESE FIELDS:

1. "category": One of: "Work", "Client", "Personal", "Family", "Finance", "Newsletter", "Promotion", "Spam", "Scam", "Government", "Social Media", "Notification", "Other"

2. "urgency": One of: "Critical", "High", "Medium", "Low", "None"

3. "spam_score": Integer 0-100 (0 = definitely legit, 100 = definitely spam/scam)

4. "is_suspicious": true/false - Flag if the email shows signs of phishing, scam, or social engineering

5. "red_flags": List of suspicious elements found (empty list if none). Look for:
   - Urgency pressure ("Act now!", "Your account will be closed")
   - Requests for personal info, passwords, or payment
   - Mismatched sender name vs email domain
   - Too-good-to-be-true offers
   - Suspicious links or attachments mentioned
   - Grammar/spelling issues typical of scam emails
   - Impersonation of known companies with wrong domains

6. "sender_type": One of: "Known Contact", "Company/Business", "Automated/Bot", "Unknown Person", "Likely Spam", "Likely Scam"

7. "suggested_action": One of: "Reply Urgently", "Reply Soon", "Reply When Free", "Read & Archive", "Ignore", "Delete", "Block Sender", "Verify Authenticity"

8. "summary": A brief 1-line human-readable summary of what this email is about

9. "ashley_note": A short witty/helpful note from Ashley about this email (1 sentence, be personality-driven)

Return ONLY valid JSON, no markdown formatting."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3,
        )

        result_text = response.choices[0].message.content.strip()

        # Clean up potential markdown wrapping
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            result_text = result_text.strip()

        return json.loads(result_text)

    except json.JSONDecodeError:
        return _fallback_analysis(sender_name, sender_email, subject, snippet)
    except Exception as e:
        print(f"[Reasoning] Analysis error: {e}")
        return _fallback_analysis(sender_name, sender_email, subject, snippet)


def _fallback_analysis(sender_name: str, sender_email: str, subject: str, snippet: str) -> dict:
    """Rule-based fallback when AI analysis fails."""
    spam_keywords = ["winner", "congratulations", "click here", "act now", "limited time",
                     "free money", "urgent action", "verify your account", "suspended",
                     "lottery", "inheritance", "prince", "million dollars", "bitcoin profit"]
    promo_keywords = ["unsubscribe", "sale", "discount", "offer", "deal", "% off", "promo"]
    newsletter_keywords = ["newsletter", "digest", "weekly", "monthly", "update from"]

    text = f"{subject} {snippet}".lower()
    email_domain = sender_email.split("@")[-1].lower() if "@" in sender_email else ""

    # Spam detection
    spam_score = 0
    red_flags = []

    for kw in spam_keywords:
        if kw in text:
            spam_score += 20
            red_flags.append(f"Contains spam keyword: '{kw}'")

    if email_domain in ["noreply", "no-reply"] or ".xyz" in email_domain or ".click" in email_domain:
        spam_score += 15
        red_flags.append(f"Suspicious domain: {email_domain}")

    spam_score = min(spam_score, 100)

    # Categorization
    if spam_score >= 60:
        category = "Spam"
    elif any(kw in text for kw in promo_keywords):
        category = "Promotion"
    elif any(kw in text for kw in newsletter_keywords):
        category = "Newsletter"
    else:
        category = "Other"

    return {
        "category": category,
        "urgency": "None" if spam_score >= 40 else "Medium",
        "spam_score": spam_score,
        "is_suspicious": spam_score >= 40,
        "red_flags": red_flags,
        "sender_type": "Likely Spam" if spam_score >= 60 else "Unknown Person",
        "suggested_action": "Delete" if spam_score >= 60 else "Read & Archive",
        "summary": f"Email from {sender_name} about: {subject}",
        "ashley_note": "Couldn't run full analysis, but here's a basic assessment.",
    }
