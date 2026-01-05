"""AI Writer + Critic (Critic-Refiner) loop for the cognitive layer.

HYBRID STRATEGY: Supports both OpenRouter API (primary) and local Ollama (fallback).
Returns script_text and visual_scenes for asset selection.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import requests


OLLAMA_BASE = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"


def load_cache(path: str) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["timestamp"]) if path else pd.DataFrame()


def pct_change_series(series: pd.Series) -> float:
    if len(series) < 2:
        return 0.0
    return (series.iloc[-1] - series.iloc[0]) / series.iloc[0] * 100.0


def slope(series: pd.Series) -> float:
    if len(series) < 2:
        return 0.0
    x = np.arange(len(series))
    y = np.array(series)
    m, _ = np.polyfit(x, y, 1)
    return float(m)


def compute_metrics(df: pd.DataFrame, symbol: str, days: int = 5) -> Optional[Dict[str, Any]]:
    sdf = df[df["symbol"] == symbol].sort_values("timestamp")
    if sdf.empty:
        return None
    recent = sdf.tail(days)
    pct = pct_change_series(recent["close"]) if len(recent) >= 2 else 0.0
    sl = slope(recent["close"]) if len(recent) >= 2 else 0.0
    mom = 0.0
    if len(sdf) >= 30:
        mom = (sdf["close"].iloc[-1] - sdf["close"].iloc[-30]) / sdf["close"].iloc[-30] * 100.0
    vol_avg = sdf["volume"].iloc[-21:-1].mean() if len(sdf) > 2 else sdf["volume"].mean()
    last_vol = int(sdf["volume"].iloc[-1])
    vol_mult = float(last_vol / vol_avg) if vol_avg and not np.isnan(vol_avg) else 1.0

    return {
        "symbol": symbol,
        "close": float(sdf["close"].iloc[-1]),
        "pct_change": round(float(pct), 4),
        "slope": round(float(sl), 6),
        "momentum_30d": round(float(mom), 4),
        "volume": last_vol,
        "vol_mult": round(float(vol_mult), 2),
    }


def build_records(df: pd.DataFrame, symbols: List[str], days: int = 5) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for sym in symbols:
        m = compute_metrics(df, sym, days=days)
        if m:
            records.append(m)
    return records


def call_openrouter(messages: List[Dict[str, str]], model: str = OPENROUTER_MODEL, timeout: int = 60) -> str:
    """Call OpenRouter API for script generation.
    
    Returns the text content of the response.
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/auto-market-pulse",
        "X-Title": "Auto Market Pulse"
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 2048
    }
    
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=timeout)
        if r.status_code == 200:
            j = r.json()
            if isinstance(j, dict) and "choices" in j and j["choices"]:
                return j["choices"][0].get("message", {}).get("content", "")
        raise RuntimeError(f"OpenRouter API returned status {r.status_code}: {r.text}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to call OpenRouter API: {e}")


def call_ollama(messages: List[Dict[str, str]], model: str = DEFAULT_MODEL, timeout: int = 60, temperature: float = 0.2, max_tokens: int = 512) -> str:
    """Call Ollama's /api/chat endpoint, fallback to /api/generate.

    Returns the text content of the response.
    """
    base = OLLAMA_BASE.rstrip("/")
    url = f"{base}/api/chat"
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        if r.status_code == 200:
            j = r.json()
            if isinstance(j, dict) and "choices" in j and j["choices"]:
                return j["choices"][0].get("message", {}).get("content", "")
            return j.get("text", "") or json.dumps(j)
    except Exception:
        pass

    # fallback to /api/generate
    try:
        url2 = f"{base}/api/generate"
        prompt = "\n".join([m.get("content", "") for m in messages if m.get("role") in ("system", "user")])
        r2 = requests.post(url2, json={"model": model, "prompt": prompt, "temperature": temperature, "max_tokens": max_tokens}, timeout=timeout)
        if r2.status_code == 200:
            j2 = r2.json()
            return j2.get("text", json.dumps(j2))
    except Exception as e:
        raise RuntimeError(f"Failed to call Ollama: {e}")

    raise RuntimeError("Ollama did not return a usable response")


def call_llm_hybrid(messages: List[Dict[str, str]], model: Optional[str] = None, timeout: int = 60) -> str:
    """Hybrid LLM caller: Try OpenRouter first, fallback to Ollama.
    
    Args:
        messages: List of message dicts with 'role' and 'content'
        model: Optional model override (ignored for OpenRouter, used for Ollama)
        timeout: Request timeout
        
    Returns:
        Response text from LLM
    """
    # Try OpenRouter first if API key is available
    if OPENROUTER_API_KEY:
        try:
            print("Attempting OpenRouter API...", file=sys.stderr)
            return call_openrouter(messages, timeout=timeout)
        except Exception as e:
            print(f"OpenRouter failed: {e}, falling back to Ollama...", file=sys.stderr)
    
    # Fallback to Ollama
    print("Using local Ollama...", file=sys.stderr)
    ollama_model = model or DEFAULT_MODEL
    return call_ollama(messages, model=ollama_model, timeout=timeout, max_tokens=2048)


# --- Prompts for Hybrid Strategy ---
WRITER_PROMPT_HYBRID = (
    "System: You are a Writer agent for short-form financial video narration.\n"
    "Goal: Generate a compelling script with visual scene mappings.\n"
    "Output Format: Return a JSON object with these keys:\n"
    "- 'script_text': The full spoken script text (word-for-word transcript)\n"
    "- 'visual_scenes': Array of scene objects, each with:\n"
    "  * 'start': Start time in seconds (float)\n"
    "  * 'end': End time in seconds (float)\n"
    "  * 'filename': Background video filename (e.g., 'vintage_1970s_home.mp4', 'money_printer_brrr.mp4')\n"
    "  * 'search_query': Optional search query for asset generation (if filename not provided)\n"
    "The script_text should be approximately 140-160 words for a 60-second video.\n"
    "Visual scenes should cover the entire script duration with appropriate transitions."
)

WRITER_PROMPT = (
    "System: You are the Writer agent for short-form financial video narration.\n"
    "Goal: Convert the provided numerical 'records' into a concise, visual, and hook-driven 'market_pulse' story JSON.\n"
    "Requirements:\n"
    "- Output strictly valid JSON with keys: type, title, bullets (list of {symbol, text}), records, signals, summary_tweet.\n"
    "- Title should be punchy and include a date.\n"
    "- Each bullet must be highly visual (what to show on screen), have a clear hook, and be <=140 chars when possible.\n"
    "- Include 'symbol' in each bullet object.\n"
    "Tone: punchy, vivid, and optimized for 9:16 short videos."
)

CRITIC_PROMPT = (
    "System: You are the Critic agent. Given a Writer draft (JSON or text), score and provide concise, actionable feedback.\n"
    "Score on 4 axes (0-10): Hook Velocity, Rhythm, Visualizability, Loop Factor.\n"
    "Return a JSON object: {\"score\": <avg 0-10>, \"components\": {\"hook\":n,\"rhythm\":n,\"visual\":n,\"loop\":n}, \"feedback\": \"...\"}.\n"
    "Feedback must be actionable: suggest changes to hook, phrasing, or ending to improve Loop Factor."
)


def ask_writer_hybrid(prompt_text: str) -> Dict[str, Any]:
    """Ask writer to generate script with visual scenes using hybrid LLM."""
    messages = [
        {"role": "system", "content": WRITER_PROMPT_HYBRID},
        {"role": "user", "content": f"Generate a script for this topic:\n{prompt_text}\n\nReturn the JSON object with script_text and visual_scenes."},
    ]
    response = call_llm_hybrid(messages)
    return extract_json(response) or {}


def ask_writer(records: List[Dict[str, Any]], model: str, temperature: float, max_tokens: int) -> str:
    user_payload = json.dumps({"records": records}, indent=2)
    messages = [
        {"role": "system", "content": WRITER_PROMPT},
        {"role": "user", "content": "Input data:\n" + user_payload + "\nProduce the story JSON now."},
    ]
    return call_ollama(messages, model=model, temperature=temperature, max_tokens=max_tokens)


def ask_critic(draft: str, model: str, temperature: float, max_tokens: int) -> str:
    messages = [
        {"role": "system", "content": CRITIC_PROMPT},
        {"role": "user", "content": "Draft:\n" + draft + "\nRespond with the scoring JSON."},
    ]
    return call_ollama(messages, model=model, temperature=temperature, max_tokens=max_tokens)


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    # Direct parse
    try:
        return json.loads(text)
    except Exception:
        pass
    # try to find first JSON object
    m = re.search(r"\{.*\}", text, flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def parse_critic(text: str) -> Dict[str, Any]:
    try:
        j = json.loads(text)
        if "score" in j:
            return j
    except Exception:
        pass
    # simple heuristic: find numeric scores
    nums = re.findall(r"([0-9](?:\.[0-9])?)", text)
    comps = {}
    score = 0.0
    if len(nums) >= 4:
        vals = list(map(float, nums[:4]))
        comps = {"hook": vals[0], "rhythm": vals[1], "visual": vals[2], "loop": vals[3]}
        score = sum(vals) / 4.0
    return {"score": score, "components": comps, "feedback": text}


def extract_visual_keywords(story_text: str, model: str = DEFAULT_MODEL) -> List[str]:
    """Extract 3 visual keywords from the story text using LLM."""
    keyword_prompt = (
        "System: Extract exactly 3 visual keywords from the following financial story text.\n"
        "These keywords will be used to select background videos (e.g., 'money', 'housing', 'inflation', 'crisis').\n"
        "Return ONLY a JSON array of exactly 3 lowercase keywords, e.g., [\"money\", \"inflation\", \"crisis\"].\n"
        "Do not include any other text or explanation."
    )
    
    try:
        messages = [
            {"role": "system", "content": keyword_prompt},
            {"role": "user", "content": f"Story text:\n{story_text}\n\nReturn the 3 keywords as JSON array:"},
        ]
        response = call_llm_hybrid(messages)
        
        # Try to parse JSON array
        response = response.strip()
        if response.startswith("```"):
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
        response = response.strip()
        
        try:
            keywords = json.loads(response)
            if isinstance(keywords, list) and len(keywords) >= 3:
                return [str(k).lower().strip() for k in keywords[:3]]
        except Exception:
            pass
        
        keywords = re.findall(r'"([^"]+)"', response)
        if len(keywords) >= 3:
            return [k.lower().strip() for k in keywords[:3]]
            
    except Exception as e:
        print(f"Warning: Failed to extract keywords: {e}", file=sys.stderr)
    
    # Ultimate fallback
    text_lower = story_text.lower()
    fallback_keywords = []
    common_terms = ["money", "inflation", "crisis", "housing", "market", "stock", "dollar", "fed", "economy", "price"]
    for term in common_terms:
        if term in text_lower and len(fallback_keywords) < 3:
            fallback_keywords.append(term)
    
    while len(fallback_keywords) < 3:
        fallback_keywords.append("market")
    
    return fallback_keywords[:3]


def fallback_story(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    bullets = []
    for r in records:
        txt = f"{r['symbol']} closed {r['pct_change']:+.2f}% at ${r['close']:.2f}"
        if r.get("vol_mult", 1.0) > 1.5:
            txt += f" — unusual volume: {r['vol_mult']:.1f}x avg"
        bullets.append({"symbol": r["symbol"], "text": txt})

    title = f"Market Pulse — {datetime.now().strftime('%b %d, %Y')}"
    summary = " | ".join([f"{r['symbol']} {r['pct_change']:+.2f}%" for r in records[:4]])
    return {"type": "market_pulse", "title": title, "bullets": bullets, "records": records, "signals": [], "summary_tweet": f"{summary} — snapshot"}


def critic_refiner_loop(records: List[Dict[str, Any]], model: str, temperature: float, max_tokens: int, max_iters: int = 3) -> Dict[str, Any]:
    draft = None
    last_candidate = None
    for i in range(max_iters):
        if draft is None:
            draft = ask_writer(records, model=model, temperature=temperature, max_tokens=max_tokens)
        else:
            refine_msg = "Refine this draft using previous feedback. Previous draft:\n" + draft
            draft = call_ollama([{"role": "system", "content": WRITER_PROMPT}, {"role": "user", "content": refine_msg}], model=model, temperature=temperature, max_tokens=max_tokens)

        critic_raw = ask_critic(draft, model=model, temperature=0.0, max_tokens=200)
        critic = parse_critic(critic_raw)
        score = float(critic.get("score", 0.0))

        parsed = extract_json(draft)
        if parsed and isinstance(parsed, dict) and parsed.get("bullets"):
            candidate = parsed
            candidate.setdefault("records", records)
            candidate.setdefault("type", "market_pulse")
        else:
            candidate = fallback_story(records)
        
        def words_count(s: str) -> int:
            return len(re.findall(r"\w+", s or ""))

        def validate_candidate(cand: Dict[str, Any]) -> Optional[str]:
            bullets = cand.get("bullets") or []
            if not isinstance(bullets, list) or len(bullets) < 3:
                return "Draft must contain three bullets: Hook, Evidence, Loop."
            hook = bullets[0].get("text", "") if len(bullets) > 0 else ""
            evidence = bullets[1].get("text", "") if len(bullets) > 1 else ""
            loop = bullets[2].get("text", "") if len(bullets) > 2 else ""
            total = words_count(hook) + words_count(evidence) + words_count(loop)
            if total < 130:
                return f"Total words {total} < 130: failure — increase density to 140-160 words." 
            if total < 140 or total > 160:
                return f"Total words {total} not in required 140-160 range."
            if words_count(evidence) < 100:
                return f"Evidence block too short ({words_count(evidence)} words). Must be >=100 words."
            if not re.search(r"\b(19|20)\d{2}\b|\b\d+%\b|\$\s*\d{1,3}(?:,\d{3})*\b", evidence):
                return "Evidence block must include specific numbers/dates (e.g., '1970', '40%', '$23,000')."
            return None

        validation_error = validate_candidate(candidate)
        last_candidate = candidate

        if score >= 8.0 and validation_error is None:
            return candidate

        feedback = critic.get("feedback", "Improve hooks, rhythm, visual cues, loop.")
        if validation_error:
            feedback = (feedback + " | VALIDATION: " + validation_error).strip()

        draft = json.dumps({"refine_feedback": feedback, "previous_draft": draft})
        time.sleep(0.3)

    return last_candidate or fallback_story(records)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cache", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--symbols", help="comma-separated list")
    p.add_argument("--days", type=int, default=5)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--temperature", type=float, default=0.2)
    p.add_argument("--max-tokens", type=int, default=512)
    args = p.parse_args()

    df = load_cache(args.cache)
    symbols = args.symbols.split(",") if args.symbols else sorted(df["symbol"].unique())
    records = build_records(df, symbols, days=args.days)

    try:
        story = critic_refiner_loop(records, model=args.model, temperature=args.temperature, max_tokens=args.max_tokens, max_iters=3)
    except Exception:
        story = fallback_story(records)

    outdir = os.path.dirname(args.output)
    if outdir:
        os.makedirs(outdir, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(story, f, indent=2)
    print("Wrote story:", args.output)
    
    # Generate visual keywords and save metadata
    script_text = story.get("title", "") + " " + " ".join([b.get("text", "") for b in story.get("bullets", [])])
    try:
        visual_keywords = extract_visual_keywords(script_text, model=args.model)
    except Exception as e:
        print(f"Warning: Failed to extract visual keywords: {e}", file=sys.stderr)
        visual_keywords = ["market", "finance", "chart"]
    
    # Save metadata to data/cache/current_video_metadata.json
    metadata_path = os.path.join("data", "cache", "current_video_metadata.json")
    os.makedirs(os.path.dirname(metadata_path), exist_ok=True)
    metadata = {
        "title": story.get("title", ""),
        "script": script_text,
        "visual_keywords": visual_keywords
    }
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Wrote metadata: {metadata_path}")


if __name__ == "__main__":
    main()
