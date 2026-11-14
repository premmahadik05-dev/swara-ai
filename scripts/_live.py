"""Shared helpers for the scripts that talk to the REAL Gnani API (verify_gnani.py, evaluate_noise.py)."""
from __future__ import annotations

import json
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.db import Base, make_engine, make_session_factory  # noqa: E402
from app.gnani.client import GnaniClient, GnaniError  # noqa: E402
from app.gnani.voices import stt_params, tts_params  # noqa: E402
from app.nlu.lexicon import Lexicon  # noqa: E402
from app.nlu.parser import parse_utterance  # noqa: E402
from app.seed import seed_products  # noqa: E402
from app.services import noise as nz  # noqa: E402
from app.services.catalog import load_views  # noqa: E402

# Spoken test phrases (one order each). Expected SKUs/quantities are used to check the whole chain.
# The seven languages added in 2.3.0 (mr bn ta te kn ml pa) have AUTHORED phrases (no native-speaker review); the first phrase of each is the
# sentence the app shows as that language's sample. All phrases are checked to parse to their expected order by backend/tests/test_scripts.py.
PHRASES = {
    "gu": [
        ("બે કિલો ખાંડ અને એક લિટર દૂધ આપો", [("SUGAR", 2.0), ("MILK", 1.0)]),
        ("અડધો કિલો ચા પત્તી અને એક કિલો લોટ જોઈએ", [("TEA", 0.5), ("ATTA", 1.0)]),
        ("ત્રણ કિલો બટાકા અને બે કિલો ડુંગળી", [("POTATO", 3.0), ("ONION", 2.0)]),
    ],
    "hi": [
        ("दो किलो चीनी और एक लीटर दूध दे दो", [("SUGAR", 2.0), ("MILK", 1.0)]),
        ("आधा किलो चायपत्ती और एक किलो आटा चाहिए", [("TEA", 0.5), ("ATTA", 1.0)]),
        ("तीन किलो आलू और दो किलो प्याज़", [("POTATO", 3.0), ("ONION", 2.0)]),
    ],
    "en": [
        ("two kilo sugar and one litre milk please", [("SUGAR", 2.0), ("MILK", 1.0)]),
        ("half kilo tea and one kilo flour", [("TEA", 0.5), ("ATTA", 1.0)]),
        ("three kilo potatoes and two kilo onions", [("POTATO", 3.0), ("ONION", 2.0)]),
    ],
    "hinglish": [
        ("bhai do kilo chini aur ek litre doodh chahiye", [("SUGAR", 2.0), ("MILK", 1.0)]),
        ("aadha kilo chai patti aur ek kilo atta dena", [("TEA", 0.5), ("ATTA", 1.0)]),
        ("teen kilo aloo aur do kilo pyaaz", [("POTATO", 3.0), ("ONION", 2.0)]),
    ],
    "mr": [
        ("मला दोन किलो साखर आणि एक लिटर दूध पाहिजे", [("SUGAR", 2.0), ("MILK", 1.0)]),
        ("दीड किलो कांदा आणि अडीच किलो बटाटा", [("ONION", 1.5), ("POTATO", 2.5)]),
        ("अर्धा किलो तांदूळ आणि तीन लिटर दूध", [("RICE-REGULAR", 0.5), ("MILK", 3.0)]),
    ],
    "bn": [
        ("আমার দুই কেজি চিনি আর এক লিটার দুধ লাগবে", [("SUGAR", 2.0), ("MILK", 1.0)]),
        ("দেড় কেজি পেঁয়াজ আর আড়াই কেজি আলু", [("ONION", 1.5), ("POTATO", 2.5)]),
        ("আধা কেজি চাল আর তিন লিটার দুধ", [("RICE-REGULAR", 0.5), ("MILK", 3.0)]),
    ],
    "ta": [
        ("எனக்கு இரண்டு கிலோ சர்க்கரை மற்றும் ஒரு லிட்டர் பால் வேண்டும்", [("SUGAR", 2.0), ("MILK", 1.0)]),
        ("ஒன்றரை கிலோ வெங்காயம் மற்றும் இரண்டரை கிலோ உருளைக்கிழங்கு", [("ONION", 1.5), ("POTATO", 2.5)]),
        ("அரை கிலோ அரிசி மற்றும் மூன்று லிட்டர் பால்", [("RICE-REGULAR", 0.5), ("MILK", 3.0)]),
    ],
    "te": [
        ("నాకు రెండు కిలోల చక్కెర మరియు ఒక లీటర్ పాలు కావాలి", [("SUGAR", 2.0), ("MILK", 1.0)]),
        ("ఒకటిన్నర కిలోల ఉల్లిపాయలు మరియు రెండున్నర కిలోల బంగాళాదుంపలు", [("ONION", 1.5), ("POTATO", 2.5)]),
        ("అర కిలో బియ్యం మరియు మూడు లీటర్ల పాలు", [("RICE-REGULAR", 0.5), ("MILK", 3.0)]),
    ],
    "kn": [
        ("ನನಗೆ ಎರಡು ಕಿಲೋ ಸಕ್ಕರೆ ಮತ್ತು ಒಂದು ಲೀಟರ್ ಹಾಲು ಬೇಕು", [("SUGAR", 2.0), ("MILK", 1.0)]),
        ("ಒಂದೂವರೆ ಕಿಲೋ ಈರುಳ್ಳಿ ಮತ್ತು ಎರಡೂವರೆ ಕಿಲೋ ಆಲೂಗಡ್ಡೆ", [("ONION", 1.5), ("POTATO", 2.5)]),
        ("ಅರ್ಧ ಕಿಲೋ ಅಕ್ಕಿ ಮತ್ತು ಮೂರು ಲೀಟರ್ ಹಾಲು", [("RICE-REGULAR", 0.5), ("MILK", 3.0)]),
    ],
    "ml": [
        ("എനിക്ക് രണ്ട് കിലോ പഞ്ചസാരയും ഒരു ലിറ്റർ പാലും വേണം", [("SUGAR", 2.0), ("MILK", 1.0)]),
        ("ഒന്നര കിലോ ഉള്ളിയും രണ്ടര കിലോ ഉരുളക്കിഴങ്ങും", [("ONION", 1.5), ("POTATO", 2.5)]),
        ("അര കിലോ അരിയും മൂന്ന് ലിറ്റർ പാലും", [("RICE-REGULAR", 0.5), ("MILK", 3.0)]),
    ],
    "pa": [
        ("ਮੈਨੂੰ ਦੋ ਕਿਲੋ ਖੰਡ ਅਤੇ ਇੱਕ ਲੀਟਰ ਦੁੱਧ ਚਾਹੀਦਾ ਹੈ", [("SUGAR", 2.0), ("MILK", 1.0)]),
        ("ਡੇਢ ਕਿਲੋ ਪਿਆਜ਼ ਅਤੇ ਢਾਈ ਕਿਲੋ ਆਲੂ", [("ONION", 1.5), ("POTATO", 2.5)]),
        ("ਅੱਧਾ ਕਿਲੋ ਚੌਲ ਅਤੇ ਤਿੰਨ ਲੀਟਰ ਦੁੱਧ", [("RICE-REGULAR", 0.5), ("MILK", 3.0)]),
    ],
}


@dataclass
class Env:
    settings: Settings
    client: GnaniClient
    lexicon: Lexicon
    sku_of: dict[int, str]


def make_env(settings: Optional[Settings] = None, transport=None) -> Env:
    settings = settings or Settings()
    d = Path(tempfile.mkdtemp())
    eng = make_engine(f"sqlite:///{d / 'v.db'}")
    Base.metadata.create_all(eng)
    with make_session_factory(eng)() as db:
        seed_products(db)
        db.commit()
        views = load_views(db)
    eng.dispose()
    return Env(settings, GnaniClient(settings, transport=transport), Lexicon(list(views.values())), {i: v.sku for i, v in views.items()})


@dataclass
class Row:
    lang: str
    phrase: str
    condition: str = "clean"
    tts_ms: Optional[int] = None
    stt_ms: Optional[int] = None
    voice: Optional[str] = None
    transcript: Optional[str] = None
    wer: Optional[float] = None
    cer: Optional[float] = None
    parsed: list = field(default_factory=list)
    chain_ok: Optional[bool] = None
    error: Optional[str] = None


def parsed_lines(env: Env, transcript: str, hint: Optional[str] = None):
    """The order the parser finds in a transcript. ``hint`` is the language the speaker was asked to use (what the app's selector sends)."""
    r = parse_utterance(transcript, env.lexicon, language_hint=hint)
    return [(env.sku_of[ln.product_ids[0]], float(ln.qty) if ln.qty is not None else None) for ln in r.lines if ln.resolved]


async def synth(env: Env, lang: str, phrase: str, sample_rate: int = 16000):
    voice, tts_lang = tts_params(env.settings, lang)
    res = await env.client.synthesize(phrase, language=tts_lang, voice=voice, speed=1.0, sample_rate=sample_rate)
    return res, voice


async def transcribe_row(env: Env, row: Row, wav: bytes, expected, reference: str) -> Row:
    code, fmt = stt_params(env.settings, row.lang)
    try:
        stt = await env.client.transcribe(wav, language_code=code, fmt=fmt, filename="check.wav")
    except GnaniError as exc:
        row.error = f"{exc.error_type}: {exc.user_message}"
        return row
    row.stt_ms = stt.meta.latency_ms
    row.transcript = stt.transcript
    row.wer = round(nz.wer(reference, stt.transcript), 4)
    row.cer = round(nz.cer(reference, stt.transcript), 4)
    row.parsed = parsed_lines(env, stt.transcript, row.lang) if stt.transcript else []
    row.chain_ok = row.parsed == [(s, q) for s, q in expected]
    return row


def pct(vals, p):
    v = sorted(x for x in vals if x is not None)
    return v[min(len(v) - 1, int(round(p / 100 * (len(v) - 1))))] if v else None


def save_report(name: str, payload: dict, md: str) -> Path:
    out = ROOT / "eval" / "results"
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    (out / f"{name}_{stamp}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    p = out / f"{name}_{stamp}.md"
    p.write_text(md, encoding="utf-8")
    return p
