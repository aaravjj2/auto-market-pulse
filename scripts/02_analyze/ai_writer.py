"""AI Writer + Critic (Critic-Refiner) loop for the cognitive layer.

This script queries a local Ollama instance to generate a market story JSON
matching the `generate_story.py` output schema. It implements a Writer agent
and a Critic agent in a loop: generate -> critique -> refine (up to max_iters).

Defaults to model 'llama3' but accepts `--model` to override.
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
            # Ollama chat: choices -> message -> content
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


# --- Prompts derived from the architecture spec (Section 5) ---
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

# Additional production-grade constraints (Section 7.2 override):
# The Writer MUST produce spoken, word-for-word transcript content inside the
# `bullets` array in three blocks: Hook, Evidence, Loop. Enforce strict word
# counts and structure for 60s videos.
#
# Constraints (must be enforced):
# - TOTAL WORDS: MUST be between 140 and 160 words. Anything less than 130 words
#   is a FAILURE and should be flagged for immediate rewrite.
# - STRUCTURE: bullets must contain exactly three entries in order:
#   1) Hook (one sentence) — immediate pattern interrupt.
#   2) Evidence (the meat): at least 100 words, must include specific numbers/dates
#      (e.g., "1970", "40%", "$23,000"). This is the spoken narrative body.
#   3) Loop (one sentence): connects back to the Hook and closes the transcript.
# - SYSTEM NOTE: You are not writing a summary. You are writing the full,
#   word-for-word spoken transcript. Do not use placeholders or bracketed tokens.
# - Output formatting: still return valid `market_pulse` JSON where `bullets`
#   holds these three transcript blocks as `{"symbol": "M2", "text": "..."}`.


CRITIC_PROMPT = (
    "System: You are the Critic agent. Given a Writer draft (JSON or text), score and provide concise, actionable feedback.\n"
    "Score on 4 axes (0-10): Hook Velocity, Rhythm, Visualizability, Loop Factor.\n"
    "Return a JSON object: {\"score\": <avg 0-10>, \"components\": {\"hook\":n,\"rhythm\":n,\"visual\":n,\"loop\":n}, \"feedback\": \"...\"}.\n"
    "Feedback must be actionable: suggest changes to hook, phrasing, or ending to improve Loop Factor."
)


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
        response = call_ollama(messages, model=model, temperature=0.1, max_tokens=100)
        
        # Try to parse JSON array
        response = response.strip()
        # Remove markdown code blocks if present
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
        
        # Fallback: try to extract from response text
        keywords = re.findall(r'"([^"]+)"', response)
        if len(keywords) >= 3:
            return [k.lower().strip() for k in keywords[:3]]
            
    except Exception as e:
        print(f"Warning: Failed to extract keywords: {e}", file=sys.stderr)
    
    # Ultimate fallback: extract common financial terms
    text_lower = story_text.lower()
    fallback_keywords = []
    common_terms = ["money", "inflation", "crisis", "housing", "market", "stock", "dollar", "fed", "economy", "price"]
    for term in common_terms:
        if term in text_lower and len(fallback_keywords) < 3:
            fallback_keywords.append(term)
    
    # Pad to 3 if needed
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
            # send previous draft + critic feedback as instruction to refine
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
        # Validate Writer constraints (production requirements)
        def words_count(s: str) -> int:
            return len(re.findall(r"\w+", s or ""))

        def validate_candidate(cand: Dict[str, Any]) -> Optional[str]:
            # Expect bullets array with exactly three blocks
            bullets = cand.get("bullets") or []
            if not isinstance(bullets, list) or len(bullets) < 3:
                return "Draft must contain three bullets: Hook, Evidence, Loop."
            # join texts
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
            # check evidence contains numbers/dates
            if not re.search(r"\b(19|20)\d{2}\b|\b\d+%\b|\$\s*\d{1,3}(?:,\d{3})*\b", evidence):
                return "Evidence block must include specific numbers/dates (e.g., '1970', '40%', '$23,000')."
            return None

        validation_error = validate_candidate(candidate)
        last_candidate = candidate

        # If critic score is high and validation passes, accept candidate
        if score >= 8.0 and validation_error is None:
            return candidate

        # Prefer critic feedback but append explicit validation feedback when present
        feedback = critic.get("feedback", "Improve hooks, rhythm, visual cues, loop.")
        if validation_error:
            feedback = (feedback + " | VALIDATION: " + validation_error).strip()

        # attach feedback into next draft request
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
    
    # Phase 1: Generate visual keywords and save metadata
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
