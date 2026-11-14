"""Password hashing and policy. Standard library only (hashlib.scrypt), no extra dependency.

Stored format:  scrypt$<N>$<r>$<p>$<salt b64>$<hash b64>   (the cost travels with the hash, so it can be raised later
and old hashes are upgraded the next time that person signs in).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import unicodedata

R = 8
DKLEN = 32
MIN_LEN, MAX_LEN = 10, 128

# A short built-in list of the passwords people choose most. It is NOT a breach database; see docs/AUTHENTICATION.md.
COMMON = frozenset("""
password password1 password123 passw0rd p@ssw0rd p@ssword 1234567890 12345678910 0123456789 qwertyuiop qwerty123 qwerty12345
1q2w3e4r5t iloveyou123 letmein123 welcome123 welcome1234 admin12345 administrator abcd123456 abcdefghij abc1234567 changeme123
111111111 1111111111 0000000000 9876543210 987654321 123456789 1234567890123 passwordpassword googlegoogle monkey1234 dragon1234
football123 baseball123 superman123 trustno1234 sunshine123 princess123 whatever123 starwars123 michael1234 jennifer123
swaraai123 swara12345 swaraai1234 kirana12345 dukaan12345 india12345 india123456 mumbai12345 vadodara123 gujarat123
""".split())


class PasswordError(ValueError):
    """The password breaks the policy. The message is safe to show to the person."""


def _norm(pw: str) -> bytes:
    return unicodedata.normalize("NFKC", pw).encode("utf-8")


def hash_password(password: str, *, log2_n: int = 15, p: int = 3) -> str:
    n = 1 << log2_n
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(_norm(password), salt=salt, n=n, r=R, p=p, dklen=DKLEN, maxmem=256 * 1024 * 1024)
    b = lambda x: base64.b64encode(x).decode("ascii")  # noqa: E731
    return f"scrypt${n}${R}${p}${b(salt)}${b(dk)}"


def _parse(stored: str):
    try:
        scheme, n, r, p, salt, dk = stored.split("$")
        if scheme != "scrypt":
            return None
        out = int(n), int(r), int(p), base64.b64decode(salt, validate=True), base64.b64decode(dk, validate=True)
        if len(out[3]) < 8 or len(out[4]) < 16 or min(out[:3]) < 1:
            return None
        return out
    except Exception:  # noqa: BLE001 - any malformed value simply fails verification
        return None


def verify_password(password: str, stored: str) -> bool:
    parsed = _parse(stored)
    if not parsed:
        return False
    n, r, p, salt, dk = parsed
    if n > 1 << 20 or r > 16 or p > 16:  # never let a corrupted row ask for gigabytes
        return False
    try:
        got = hashlib.scrypt(_norm(password), salt=salt, n=n, r=r, p=p, dklen=len(dk), maxmem=1024 * 1024 * 1024)
    except ValueError:  # e.g. n not a power of two in a corrupted row
        return False
    return hmac.compare_digest(got, dk)


def needs_rehash(stored: str, *, log2_n: int, p: int) -> bool:
    parsed = _parse(stored)
    return not parsed or parsed[0] < (1 << log2_n) or parsed[2] < p


_DUMMY: dict[tuple[int, int], str] = {}


def dummy_verify(password: str, *, log2_n: int, p: int) -> None:
    """Spend the same time as a real check, so an unknown e-mail address answers as slowly as a known one."""
    key = (log2_n, p)
    if key not in _DUMMY:
        _DUMMY[key] = hash_password("not-a-real-password", log2_n=log2_n, p=p)
    verify_password(password, _DUMMY[key])


def check_policy(password: str, *, email: str = "", full_name: str = "") -> None:
    if len(password) < MIN_LEN:
        raise PasswordError(f"Use at least {MIN_LEN} characters.")
    if len(password) > MAX_LEN:
        raise PasswordError(f"Use at most {MAX_LEN} characters.")
    if "\x00" in password or password != password.strip():
        raise PasswordError("Remove spaces at the start or end, and any control characters.")
    low = password.lower()
    squashed = re.sub(r"[^a-z0-9]", "", low)
    if low in COMMON or squashed in COMMON:
        raise PasswordError("That password is too common. Pick something less guessable.")
    if len(set(password)) < 4:
        raise PasswordError("Use more different characters.")
    local = email.split("@")[0].lower()
    if len(local) >= 4 and local in low:
        raise PasswordError("Do not include your e-mail name in the password.")
    parts = [re.sub(r"[^a-z0-9]", "", x.lower()) for x in full_name.split()]
    if squashed in {x for x in [*parts, "".join(parts)] if len(x) >= 4}:
        raise PasswordError("Do not use your name as the password.")


def strength(password: str) -> int:
    """0-4 guide for the meter. The server enforces check_policy; this only helps people choose."""
    if not password:
        return 0
    pools = sum(bool(re.search(p, password)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    score = (len(password) >= 10) + (len(password) >= 14) + (pools >= 3) + (pools >= 4 or len(password) >= 20)
    return min(score, 4)
