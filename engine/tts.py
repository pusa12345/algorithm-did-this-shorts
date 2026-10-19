"""Free offline TTS: espeak-ng (phonemes) + Kokoro ONNX (voice).
Usage: synth(lines, voice) -> (audio float32 @24k, [(start,end) per line])
"""
import json, os, re, subprocess
import numpy as np
import onnxruntime as rt

HERE = os.path.dirname(os.path.abspath(__file__))
ESPEAK = os.path.join(HERE, "espeak/bin/espeak-ng")
ENV = dict(os.environ, ESPEAK_DATA_PATH=os.path.join(HERE, "espeak/share/espeak-ng-data"),
           LD_LIBRARY_PATH=os.path.join(HERE, "espeak/lib"))
VOCAB = json.load(open(os.path.join(HERE, "vocab.json")))["vocab"]
SR = 24000
_sess = None
_voices = None


def _ipa(chunk):
    if not chunk.strip():
        return ""
    out = subprocess.run([ESPEAK, "-q", "--ipa", "-v", "en-us", chunk],
                         capture_output=True, text=True, env=ENV).stdout
    return " ".join(out.split())


def phonemize(text):
    # keep punctuation like phonemizer(preserve_punctuation=True)
    parts = re.split(r"([,.!?;:—…])", text)
    res = ""
    for p in parts:
        if re.fullmatch(r"[,.!?;:—…]", p or ""):
            res = res.rstrip() + p + " "
        else:
            res += _ipa(p) + " "
    res = " ".join(res.split())
    return "".join(c for c in res if c in VOCAB)


def _load():
    global _sess, _voices
    if _sess is None:
        _sess = rt.InferenceSession(os.path.join(HERE, "kokoro.onnx"), providers=["CPUExecutionProvider"])
        _voices = np.load(os.path.join(HERE, "voices.bin"))
    return _sess, _voices


def say(text, voice="am_michael", speed=1.05):
    sess, voices = _load()
    ph = phonemize(text)
    toks = [VOCAB[c] for c in ph][:510]
    style = voices[voice][min(len(toks), len(voices[voice])) - 1]
    names = {i.name: i for i in sess.get_inputs()}
    tk = "input_ids" if "input_ids" in names else "tokens"
    feeds = {tk: np.array([[0, *toks, 0]], dtype=np.int64),
             "style": np.asarray(style, dtype=np.float32),
             "speed": np.array([speed], dtype=np.int32 if "int" in names["speed"].type else np.float32)}
    audio = np.asarray(sess.run(None, feeds)[0]).ravel().astype(np.float32)
    # trim silence
    idx = np.where(np.abs(audio) > 0.01)[0]
    if len(idx):
        audio = audio[max(0, idx[0] - 600): idx[-1] + 1200]
    return audio


def synth(lines, voice="am_michael", gap=0.18, speed=1.05):
    chunks, spans, t = [], [], 0.0
    for ln in lines:
        a = say(ln, voice, speed)
        spans.append((t, t + len(a) / SR))
        chunks += [a, np.zeros(int(gap * SR), np.float32)]
        t += len(a) / SR + gap
    return np.concatenate(chunks), spans


if __name__ == "__main__":
    import scipy.io.wavfile as w
    _, v = _load()
    print(list(v.keys()))
    a, s = synth(["Why does AI keep saying delve?", "Nobody talks like that."])
    w.write("/tmp/test.wav", SR, a)
    print(s)
