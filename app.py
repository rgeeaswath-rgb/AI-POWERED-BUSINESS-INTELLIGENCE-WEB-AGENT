import pandas as pd
import json
import os
import re
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from fastapi.responses import JSONResponse, Response
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from google import genai
import uvicorn
from datetime import datetime

app = FastAPI(title="AI Business Intelligence Agent API")

# Setup paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Silence favicon 404 errors
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(content=b"", media_type="image/x-icon", status_code=204)

# API Setup
API_KEYS = [
    "AIzaSyBhr510ol3vI5KA6GTPVHJ0AaaHVwvqI-I",
    "AIzaSyCO-PYoPItIPpPbqedh_0AEOfJAR6_HMww",
    "AIzaSyCiZcqEDiQHIzM0PxocKgx0BKjlmOfwUNk",
    "AIzaSyBaPpQRrP1l8qaBjfJZQGqgGJkkZ7RBkFY"
]
current_key_idx = 0
client = genai.Client(api_key=API_KEYS[current_key_idx])

def generate_with_fallback(contents, model='gemini-2.0-flash'):
    global current_key_idx, client
    last_error = None
    for _ in range(len(API_KEYS)):
        try:
            return client.models.generate_content(model=model, contents=contents)
        except Exception as e:
            last_error = e
            print(f"[API] Error encountered: {e}. Switching key...")
            current_key_idx = (current_key_idx + 1) % len(API_KEYS)
            client = genai.Client(api_key=API_KEYS[current_key_idx])
    
    print(f"[API] Fatal error: All API keys exhausted. Last error: {last_error}")
    raise Exception("All API keys exhausted or failed.")

# Load Data
try:
    df = pd.read_csv(os.path.join(BASE_DIR, "data", "Processed_Reviews.csv"))
    with open(os.path.join(BASE_DIR, "data", "top_issues.json"), "r") as f:
        top_issues = json.load(f)
    df['Date'] = pd.to_datetime(df['Date'])
except Exception as e:
    print(f"Error loading data: {e}")
    df = pd.DataFrame()
    top_issues = []

# --- NLP INTENT ENGINE ---
intent_data = {
    "overall_sentiment": ["what is overall customer sentiment", "how do people feel generally", "general mood", "are customers happy", "sentiment summary"],
    "top_complaints": ["what are the top complaints", "main issues", "what do people hate", "problems", "negative feedback", "what are the complaints"],
    "sentiment_trend": ["how has sentiment changed over time", "show me a trend", "is sentiment getting better or worse", "sentiment shifts"],
    "average_rating": ["what is the average rating", "average score", "how many stars", "rating distribution"],
    "search": ["what do people say about", "search reviews for", "find reviews containing", "opinions on", "search for", "look for reviews related to", "tell me about", "reviews of", "information on", "what do people think of", "what do people think about", "thoughts on", "what about", "what are the reviews about", "reviews about", "show me reviews about", "search about", "what are people saying about"]
}

corpus = []
intent_labels = []
for intent, phrases in intent_data.items():
    for phrase in phrases:
        corpus.append(phrase)
        intent_labels.append(intent)

vectorizer = TfidfVectorizer()
X_train = vectorizer.fit_transform(corpus)

def predict_intent(query):
    query_vec = vectorizer.transform([query])
    similarities = cosine_similarity(query_vec, X_train)[0]
    best_match_idx = similarities.argmax()
    if similarities[best_match_idx] > 0.15:
        return intent_labels[best_match_idx]
    return "unknown"

# --- API ROUTES ---

@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/api/kpis")
async def get_kpis():
    if df.empty:
        return {"error": "No data loaded"}
    
    total_reviews = len(df)
    avg_rating = df['Score'].mean() if 'Score' in df.columns else 0
    avg_sent = df['Sentiment_Score'].mean() if 'Sentiment_Score' in df.columns else 0
    pos_pct = (len(df[df['Sentiment'] == 'Positive']) / total_reviews * 100) if total_reviews > 0 else 0
    
    return {
        "total_reviews": f"{total_reviews:,}",
        "avg_rating": round(avg_rating, 2),
        "avg_sentiment": round(avg_sent, 2),
        "positive_percent": round(pos_pct, 1)
    }

@app.get("/api/charts")
async def get_charts():
    if df.empty:
        return {"error": "No data loaded"}
    
    # Sentiment Trend
    monthly_trend = df.groupby('Month_Year')['Sentiment_Score'].mean().sort_index()
    trend_data = {
        "labels": monthly_trend.index.tolist(),
        "data": monthly_trend.values.tolist()
    }
    
    # Sentiment Pie
    sentiment_counts = df['Sentiment'].value_counts()
    pie_data = {
        "labels": sentiment_counts.index.tolist(),
        "data": sentiment_counts.values.tolist()
    }
    
    # Rating Bar
    rating_counts = df['Score'].value_counts().sort_index()
    rating_data = {
        "labels": rating_counts.index.tolist(),
        "data": rating_counts.values.tolist()
    }
    
    return {
        "trend": trend_data,
        "pie": pie_data,
        "ratings": rating_data
    }

@app.post("/api/chat")
async def chat(request: Request):
    data = await request.json()
    query = data.get("query", "").lower()
    if not query:
        return {"response": "Please ask a question."}
    
    intent = predict_intent(query)
    
    if intent == "overall_sentiment":
        counts = df['Sentiment'].value_counts()
        total = len(df)
        resp = "The overall customer sentiment is as follows:\n"
        for sent, count in counts.items():
            resp += f"- {sent}: {count} reviews ({count/total*100:.1f}%)\n"
        resp += "\nYou can see the detailed breakdown in the 'Sentiment Distribution' chart."
        return {"response": resp}
        
    elif intent == "top_complaints":
        negative_reviews = df[df['Sentiment'] == 'Negative']['Text'].dropna().head(50).tolist()
        sample_text = " ".join([re.sub(r'<[^>]+>', ' ', str(t)) for t in negative_reviews])
        try:
            ai_resp = generate_with_fallback(
                contents=f'Identify top 3 products and complaints from these reviews: {sample_text}'
            )
            return {"response": ai_resp.text.strip()}
        except:
            return {"response": "Top issues include: " + ", ".join(top_issues)}
            
    elif intent == "sentiment_trend":
        return {"response": "The sentiment trend chart on the dashboard shows how customer satisfaction has evolved over time. Currently, the average sentiment score is " + str(round(df['Sentiment_Score'].mean(), 2)) + "."}
        
    elif intent == "average_rating":
        avg = df['Score'].mean()
        return {"response": f"The average customer rating is {avg:.2f} out of 5 stars based on {len(df)} reviews."}
        
    elif intent == "search":
        # Extract keyword deterministically (No API needed)
        prefixes = [
            "what are the reviews about", "show me reviews about", "search about",
            "what are people saying about", "what do people say about", "search reviews for",
            "find reviews containing", "opinions on", "search for", "look for reviews related to",
            "look for", "reviews about", "tell me about", "reviews of", "information on",
            "what do people think of", "what do people think about", "thoughts on", "what about",
            "what are the"
        ]
        
        keyword = query
        for prefix in prefixes:
            if keyword.startswith(prefix):
                keyword = keyword[len(prefix):].strip()
                break
                
        # Clean up any weird punctuation left behind
        keyword = re.sub(r'[^\w\s]', '', keyword).strip()
        if not keyword: return {"response": "What would you like to search for?"}
        
        mask = df['CleanText'].astype(str).str.contains(keyword, case=False, na=False)
        results = df[mask]
        
        if results.empty:
            return {"response": f"I couldn't find any reviews mentioning '{keyword}'."}

        # Calculate general mood
        avg_sent = results['Sentiment_Score'].mean()
        mood = "Positive" if avg_sent > 0.1 else ("Negative" if avg_sent < -0.1 else "Neutral")

        # Generate Local Statistical Summary (No API needed)
        try:
            # Extract top keywords using our existing TF-IDF tool
            from sklearn.feature_extraction.text import TfidfVectorizer
            vec = TfidfVectorizer(stop_words='english', max_features=8)
            vec.fit(results['CleanText'].dropna().astype(str))
            
            # Filter out the search keyword itself from the themes
            top_words = [w for w in vec.get_feature_names_out() if w.lower() not in keyword.lower()][:5]
            
            pos_pct = round((len(results[results['Sentiment'] == 'Positive']) / len(results)) * 100)
            neg_pct = round((len(results[results['Sentiment'] == 'Negative']) / len(results)) * 100)
            
            summary = f"Customers generally feel {mood.lower()} about '{keyword.capitalize()}'. "
            summary += f"Approximately {pos_pct}% of the reviews are positive, while {neg_pct}% are negative. "
            if top_words:
                summary += f"When discussing this, people frequently mention themes like: {', '.join(top_words)}."
        except:
            summary = f"Based on {len(results)} reviews, the general sentiment is {mood}."

        # Prepare sample reviews summaries (Using the dataset's built-in 'Summary' column)
        sample_list = []
        for i, (_, row) in enumerate(results.head(3).iterrows()):
            rev_summary = str(row.get('Summary', ''))
            rev_summary = re.sub(r'<[^>]+>', '', rev_summary).strip()
            
            # If there's no native summary, just take the first 80 characters of the text
            if len(rev_summary) < 3 or rev_summary.lower() == 'nan':
                rev_summary = str(row.get('Text', ''))[:80] + "..."
            
            # Clean up quotes
            rev_summary = rev_summary.replace('&quot;', '"')
            sample_list.append(rev_summary)

        # Calculate Rubric Score
        rubric_score = round(results['Score'].mean()) if not results['Score'].empty else 0
        rubric_word = "Excellent" if rubric_score == 5 else ("Good" if rubric_score == 4 else ("Average" if rubric_score == 3 else ("Poor" if rubric_score == 2 else "Terrible")))

        # Build professional response matching the desired layout
        resp = f"Searching the review database...\n\n"
        resp += f"--- Search Results for '{keyword.capitalize()}' ---\n"
        resp += f"Found {len(results)} reviews mentioning '{keyword.capitalize()}'.\n"
        resp += f"General mood about '{keyword.capitalize()}': {mood}\n"
        resp += f"Rubric Score: {rubric_word} / {rubric_score} Stars\n\n"
        
        resp += "Sample reviews:\n"
        for s in sample_list:
            resp += f"* {s}\n"
            
        resp += "\n--- Summary ---\n"
        resp += f"Overall, the sentiment for '{keyword.capitalize()}' is {mood}.\n\n"
        resp += f"{summary}"
        
        return {"response": resp}
    
    else:
        # Generic AI Response for unknown intents
        try:
            ai_resp = generate_with_fallback(contents=f"User asked: {query}. Respond as a Business Intelligence assistant. Be professional.")
            return {"response": ai_resp.text.strip()}
        except:
            return {"response": "I'm sorry, I couldn't process that request. Try asking about overall sentiment or top complaints."}

@app.get("/api/wordcloud")
async def get_wordcloud():
    try:
        if df.empty or 'Summary' not in df.columns:
            return {"words": []}
            
        # Use CountVectorizer to get top word frequencies
        vectorizer = CountVectorizer(stop_words='english', max_features=50)
        word_counts = vectorizer.fit_transform(df['Summary'].dropna())
        
        words = vectorizer.get_feature_names_out()
        counts = word_counts.sum(axis=0).A1
        
        # Create list of dicts
        word_list = [{"text": word, "size": int(count)} for word, count in zip(words, counts)]
        
        # Sort by size descending
        word_list.sort(key=lambda x: x["size"], reverse=True)
        return {"words": word_list}
    except Exception as e:
        print(f"Error generating word cloud data: {e}")
        return {"words": []}

@app.post("/api/rate")
async def rate_ui(request: Request):
    try:
        data = await request.json()
        rating = data.get("rating")
        comment = data.get("comment", "")
        
        feedback_file = os.path.join(BASE_DIR, "data", "ui_ratings.json")
        
        # Load existing feedback
        if os.path.exists(feedback_file):
            with open(feedback_file, "r") as f:
                feedbacks = json.load(f)
        else:
            feedbacks = []
            
        feedbacks.append({
            "timestamp": datetime.now().isoformat(),
            "rating": rating,
            "comment": comment
        })
        
        # Save feedback
        with open(feedback_file, "w") as f:
            json.dump(feedbacks, f, indent=4)
            
        return {"status": "success", "message": "Rating saved successfully."}
    except Exception as e:
        print(f"Error saving rating: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
