"""Noise Lab maths. Noise here is SYNTHETIC (generated); it models SNR and band-limiting, not a real shop."""
from __future__ import annotations

import numpy as np
import pytest

from app.services import noise as nz

from .helpers import AuthedClient, KEY, make_wav


@pytest.mark.parametrize("kind", nz.NOISE_KINDS)
@pytest.mark.parametrize("snr", [0, 10, 20])
def test_measured_snr_matches_requested(kind, snr):
    d = nz.degrade(make_wav(2.0), kind=kind, snr_db=snr)
    assert d.measured_snr_db == pytest.approx(snr, abs=0.6)


def test_degrade_is_deterministic_per_seed():
    a = nz.degrade(make_wav(1.0), kind="babble", snr_db=5, seed=3).wav
    b = nz.degrade(make_wav(1.0), kind="babble", snr_db=5, seed=3).wav
    c = nz.degrade(make_wav(1.0), kind="babble", snr_db=5, seed=4).wav
    assert a == b and a != c


def test_output_is_16k_mono_pcm16_and_not_clipped():
    d = nz.degrade(make_wav(1.0, sr=44100), kind="white", snr_db=-5)
    x, sr = nz.read_wav(d.wav)
    assert sr == 16000 and x.ndim == 1 and np.max(np.abs(x)) <= 1.0


def test_telephony_removes_out_of_band_energy():
    sr = 16000
    t = np.arange(sr) / sr
    x = (np.sin(2 * np.pi * 100 * t) + np.sin(2 * np.pi * 1000 * t) + np.sin(2 * np.pi * 6000 * t)).astype(np.float32) * 0.2
    y = nz.telephony(x, sr)
    spec = np.abs(np.fft.rfft(y))
    f = np.fft.rfftfreq(len(y), 1 / sr)
    band = lambda lo, hi: spec[(f >= lo) & (f <= hi)].max()
    assert band(900, 1100) > 10 * band(5900, 6100) and band(900, 1100) > 5 * band(80, 120)


def test_stereo_and_non_wav_inputs():
    x, sr = nz.read_wav(make_wav(0.5, channels=2))
    assert x.ndim == 1
    with pytest.raises(nz.AudioFormatError):
        nz.read_wav(b"not a wav file at all, definitely")
    with pytest.raises(nz.AudioFormatError):
        nz.degrade(make_wav(0.05), kind="white", snr_db=10)
    with pytest.raises(ValueError):
        nz.degrade(make_wav(1.0), kind="rain", snr_db=10)
    with pytest.raises(ValueError):
        nz.degrade(make_wav(1.0), kind="white", snr_db=None)


def test_wer_cer_known_values():
    assert nz.wer("do kilo chini", "do kilo chini") == 0
    assert nz.wer("do kilo chini", "do kilo") == pytest.approx(1 / 3)
    assert nz.wer("do kilo chini", "teen kilo cheeni") == pytest.approx(2 / 3)
    assert nz.wer("a b c d", "") == 1.0
    assert nz.wer("", "") == 0.0
    assert nz.cer("abcd", "abxd") == pytest.approx(0.25)
    assert nz.wer("DO Kilo, Chini!", "do kilo chini") == 0  # case / punctuation insensitive
    assert nz.wer("૨ કિલો ખાંડ", "2 કિલો ખાંડ") == 0  # digit-script insensitive


def test_noise_endpoints(make_app):
    import httpx
    with AuthedClient(make_app(gnani_api_key=KEY)) as c:
        r = c.post("/api/noise/preview", files={"audio": ("a.wav", make_wav(1.0), "audio/wav")}, data={"kind": "pink", "snr_db": "10"})
        assert r.status_code == 200 and r.content[:4] == b"RIFF" and r.headers["x-condition"] == "pink@10dB"
        assert abs(float(r.headers["x-measured-snr-db"]) - 10) < 0.7
        bad = c.post("/api/noise/preview", files={"audio": ("a.wav", make_wav(1.0), "audio/wav")}, data={"kind": "rain", "snr_db": "10"})
        assert bad.status_code == 422
        assert c.post("/api/noise/preview", files={"audio": ("a.mp3", b"ID3" + b"\0" * 100, "audio/mpeg")}).status_code == 415
        assert c.post("/api/noise/run", files={"audio": ("a.wav", make_wav(1.0), "audio/wav")}, data={"conditions": "[{\"kind\":\"rain\",\"snr_db\":5}]"}).status_code == 422


def test_noise_run_requires_key(client):
    r = client.post("/api/noise/run", files={"audio": ("a.wav", make_wav(1.0), "audio/wav")},
                    data={"conditions": '[{"kind":"white","snr_db":10}]'})
    assert r.status_code == 503


def test_noise_run_with_simulated_gnani_reports_wer_per_condition(make_app):
    import httpx
    outputs = iter(["do kilo chini", "do kilo cheeni aur", "kilo", "", "do kilo chini"])

    def handler(req):
        return httpx.Response(200, json={"success": True, "transcript": next(outputs), "model": "prisma-v2.5", "request_id": "x"})

    app = make_app(gnani_api_key=KEY)
    app.state.gnani._transport = httpx.MockTransport(handler)
    conds = '[{"kind":"white","snr_db":20},{"kind":"babble","snr_db":0},{"telephony":true}]'
    with AuthedClient(app) as c:
        r = c.post("/api/noise/run", files={"audio": ("a.wav", make_wav(1.0), "audio/wav")},
                   data={"conditions": conds, "language": "hi", "reference_text": "do kilo chini"})
    assert r.status_code == 200, r.text
    rows = r.json()["results"]
    assert [x["label"] for x in rows] == ["clean", "white@20dB", "babble@0dB", "telephony"]
    assert rows[0]["wer"] == 0 and rows[1]["wer"] == pytest.approx(2 / 3, abs=1e-3) and rows[3]["wer"] == 1.0
    assert rows[0]["parsed_lines"][0]["product"] == "Sugar"
