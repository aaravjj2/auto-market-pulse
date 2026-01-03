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
    # Backend priority: pyttsx3 (offline), Coqui TTS (local), gTTS (online)
    if backend in ('auto', 'pyttsx3'):
        try:
            import pyttsx3

            engine = pyttsx3.init()
            engine.setProperty("rate", 150)
            engine.save_to_file(text, out_wav)
            engine.runAndWait()
            return
        except Exception:
            if backend == 'pyttsx3':
                raise
            print("pyttsx3 unavailable, trying next backend")

    if backend in ('auto', 'coqui'):
        try:
            # Coqui TTS (package `TTS`) — local, higher-quality models if installed
            from TTS.api import TTS

            # use the default local model (will download if first-run and internet available)
            tts = TTS(list_models()[0]) if False else TTS("tts_models/en/ljspeech/tacotron2-DDC")
            # synthesize to wav
            tts.tts_to_file(text=text, file_path=out_wav)
            return
        except Exception as e:
            print("Coqui TTS unavailable or failed:", e)
            if backend == 'coqui':
                raise
            print("falling back to gTTS")

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
        segments.append((b.get("text", ""), timing.get("scene_sec", 4)))
    # outro
    segments.append(("End — Educational content. Not financial advice.", timing.get("outro_sec", 2)))

    tmpdir = os.path.join(os.path.dirname(args.output), "_audio_tmp")
    os.makedirs(tmpdir, exist_ok=True)

    prepared = []
    for i, (text, dur) in enumerate(segments):
        wav = os.path.join(tmpdir, f"seg_{i:02d}.wav")
        wav_fixed = os.path.join(tmpdir, f"seg_{i:02d}.fixed.wav")
        print(f"Synthesizing segment {i}: {text[:80]}")
        tts_save(text, wav)
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
    args = p.parse_args()
    main(args)
