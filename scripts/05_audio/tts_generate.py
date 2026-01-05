#!/usr/bin/env python3
"""Synthesize per-scene TTS audio, pad/trim to scene durations, and concat into one audio file.

Outputs a WAV file aligned to the video timing in the story.
"""
import argparse
import json
import os
import subprocess
import tempfile
import uuid
import shlex
import wave


def get_ffmpeg():
    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        return get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def run(cmd):
    print("RUN:", cmd)
    subprocess.run(cmd, shell=True, check=True)


def tts_save(text, out_wav, backend='auto'):
    # Replace previous backends with Edge-TTS (async) per Architecture Section 7.2
    # Hardcode production voice per spec: en-US-ChristopherNeural
    voice = "en-US-ChristopherNeural"

    import asyncio
    try:
        import edge_tts
    except Exception as e:
        raise RuntimeError(f"edge-tts package not available: {e}")

    async def _synth_and_save(text, mp3_path, voice_name):
        communicate = edge_tts.Communicate(text, voice=voice_name)
        await communicate.save(mp3_path)

    # edge-tts outputs MP3; synthesize then convert to WAV using ffmpeg
    mp3_tmp = out_wav + ".edge.mp3"
    try:
        asyncio.run(_synth_and_save(text, mp3_tmp, voice))
    except Exception as e:
        # surface error clearly
        raise RuntimeError(f"Edge-TTS synthesis failed: {e}")

    # convert mp3 to wav
    ffmpeg = get_ffmpeg()
    ff = shlex.quote(ffmpeg)
    cmd = f"{ff} -y -i {shlex.quote(mp3_tmp)} -ar 44100 -ac 2 {shlex.quote(out_wav)}"
    run(cmd)
    try:
        os.remove(mp3_tmp)
    except Exception:
        pass


def tts_save_via_http(text, out_wav, coqui_url):
    """Try calling a local Coqui TTS HTTP service. Tries common endpoints."""
    try:
        import requests
    except Exception:
        raise RuntimeError("requests package required for HTTP Coqui TTS")

    endpoints = [
        f"{coqui_url.rstrip('/')}/api/tts",
        f"{coqui_url.rstrip('/')}/tts",
        f"{coqui_url.rstrip('/')}/api/generate",
    ]

    headers = {"Content-Type": "application/json"}
    payload = {"text": text}

    for ep in endpoints:
        try:
            print("Trying Coqui HTTP endpoint:", ep)
            r = requests.post(ep, json=payload, headers=headers, timeout=20)
            if r.status_code == 200:
                # If response is audio bytes, save directly
                content_type = r.headers.get('Content-Type', '')
                if 'audio' in content_type or r.content.startswith(b"RIFF") or r.content.startswith(b"\x52\x49\x46\x46"):
                    with open(out_wav, 'wb') as f:
                        f.write(r.content)
                    return True
                # If JSON with base64 field
                try:
                    j = r.json()
                    if isinstance(j, dict):
                        for k in ('wav','audio','output'):
                            if k in j and isinstance(j[k], str):
                                import base64
                                b = base64.b64decode(j[k])
                                with open(out_wav, 'wb') as f:
                                    f.write(b)
                                return True
                except Exception:
                    pass
            else:
                print(f"Coqui endpoint {ep} returned status {r.status_code}")
        except Exception as e:
            print("Coqui HTTP attempt failed for", ep, "->", e)
    return False

    # fallback: gTTS -> mp3 -> convert to wav via ffmpeg
    try:
        from gtts import gTTS
    except Exception:
        raise RuntimeError("No TTS backend available (pyttsx3/coqui failed and gTTS not installed)")

    t = gTTS(text)
    tmpmp3 = out_wav + ".mp3"
    t.save(tmpmp3)
    ffmpeg = get_ffmpeg()
    ff = shlex.quote(ffmpeg)
    cmd = f"{ff} -y -i {shlex.quote(tmpmp3)} -ar 44100 -ac 2 {shlex.quote(out_wav)}"
    run(cmd)
    os.remove(tmpmp3)


def ffprobe_duration(ffmpeg, fpath):
    # Prefer wave module for WAV files
    try:
        with wave.open(fpath, 'rb') as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate)
    except Exception:
        # fallback to ffprobe if available
        ffprobe = shlex.quote(ffmpeg).replace('ffmpeg', 'ffprobe')
        cmd = f"{ffprobe} -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {shlex.quote(fpath)}"
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if p.returncode != 0:
            return 0.0
        try:
            return float(p.stdout.strip())
        except Exception:
            return 0.0


def make_silence(ffmpeg, seconds, outpath):
    ff = shlex.quote(ffmpeg)
    cmd = f"{ff} -y -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 -t {seconds} -q:a 9 -ac 2 -ar 44100 {shlex.quote(outpath)}"
    run(cmd)


def pad_or_trim(ffmpeg, inpath, target_dur, outpath):
    dur = ffprobe_duration(ffmpeg, inpath)
    if dur >= target_dur - 0.01:
        # trim
        ff = shlex.quote(ffmpeg)
        cmd = f"{ff} -y -i {shlex.quote(inpath)} -t {target_dur} -ac 2 -ar 44100 {shlex.quote(outpath)}"
        run(cmd)
    else:
        # pad with silence
        tmp_sil = outpath + ".sil.wav"
        make_silence(ffmpeg, target_dur - dur, tmp_sil)
        listf = outpath + ".list.txt"
        with open(listf, "w") as f:
            f.write(f"file '{os.path.abspath(inpath)}'\n")
            f.write(f"file '{os.path.abspath(tmp_sil)}'\n")
        ff = shlex.quote(ffmpeg)
        cmd = f"{ff} -y -f concat -safe 0 -i {shlex.quote(listf)} -c copy {shlex.quote(outpath)}"
        run(cmd)
        os.remove(listf)
        os.remove(tmp_sil)


def concat_list(ffmpeg, files, outpath):
    listf = outpath + ".list.txt"
    with open(listf, "w") as f:
        for p in files:
            f.write(f"file '{os.path.abspath(p)}'\n")
    ff = shlex.quote(ffmpeg)
    cmd = f"{ff} -y -f concat -safe 0 -i {shlex.quote(listf)} -c copy {shlex.quote(outpath)}"
    run(cmd)
    os.remove(listf)


def main(args):
    with open(args.story) as f:
        story = json.load(f)
    with open(args.timing) as f:
        timing = json.load(f)

    ffmpeg = get_ffmpeg()

    segments = []
    # intro
    intro_text = story.get("title", "Market Pulse")
    segments.append((intro_text, timing.get("intro_sec", 3)))
    # bullets
    for b in story.get("bullets", []):
        # allow per-bullet duration via 'dur' (seconds); otherwise use scene_sec
        dur = b.get("dur") if isinstance(b.get("dur"), (int, float)) else timing.get("scene_sec", 4)
        segments.append((b.get("text", ""), dur))
    # outro
    segments.append(("End — Educational content. Not financial advice.", timing.get("outro_sec", 2)))

    tmpdir = os.path.join(os.path.dirname(args.output), "_audio_tmp")
    os.makedirs(tmpdir, exist_ok=True)

    prepared = []
    for i, (text, dur) in enumerate(segments):
        wav = os.path.join(tmpdir, f"seg_{i:02d}.wav")
        wav_fixed = os.path.join(tmpdir, f"seg_{i:02d}.fixed.wav")
        print(f"Synthesizing segment {i}: {text[:80]}")
        # If a Coqui HTTP URL is provided, try it first when requested
        used = False
        if getattr(args, 'coqui_url', None) and args.backend in ('auto', 'coqui'):
            try:
                ok = tts_save_via_http(text, wav, args.coqui_url)
                if ok:
                    used = True
            except Exception as e:
                print('Coqui HTTP TTS attempt failed:', e)

        if not used:
            tts_save(text, wav, backend=args.backend)
        pad_or_trim(ffmpeg, wav, dur, wav_fixed)
        prepared.append(wav_fixed)

    concat_list(ffmpeg, prepared, args.output)
    print("Wrote audio:", args.output)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--story", required=True)
    p.add_argument("--timing", default="templates/video_timing.json")
    p.add_argument("--output", required=True)
    p.add_argument("--backend", choices=['auto','pyttsx3','coqui','gtts'], default='auto', help='TTS backend to prefer')
    p.add_argument("--coqui-url", default=None, help='URL of local Coqui TTS HTTP server (e.g. http://localhost:5002)')
    args = p.parse_args()
    main(args)
