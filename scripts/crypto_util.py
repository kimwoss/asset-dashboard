# -*- coding: utf-8 -*-
"""파일 암호화/복호화 (AES-256-GCM + PBKDF2-SHA256).

대시보드(WebCrypto)와 동일한 포맷의 JSON 봉투를 사용한다:
  {"v":1, "iter":600000, "salt":b64, "iv":b64, "ct":b64}

사용법:
  python crypto_util.py encrypt <입력파일> <출력.enc>
  python crypto_util.py decrypt <입력.enc> <출력파일>
비밀번호는 환경변수 ASSET_PASSPHRASE 또는 프롬프트로 입력.
"""
import base64
import getpass
import json
import os
import sys

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERATIONS = 600_000


def _derive(passphrase: str, salt: bytes, iterations: int = ITERATIONS) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt_bytes(data: bytes, passphrase: str) -> str:
    salt, iv = os.urandom(16), os.urandom(12)
    ct = AESGCM(_derive(passphrase, salt)).encrypt(iv, data, None)
    return json.dumps({
        "v": 1, "iter": ITERATIONS,
        "salt": base64.b64encode(salt).decode(),
        "iv": base64.b64encode(iv).decode(),
        "ct": base64.b64encode(ct).decode(),
    })


def decrypt_bytes(envelope: str, passphrase: str) -> bytes:
    o = json.loads(envelope)
    key = _derive(passphrase, base64.b64decode(o["salt"]), o.get("iter", ITERATIONS))
    return AESGCM(key).decrypt(base64.b64decode(o["iv"]), base64.b64decode(o["ct"]), None)


def encrypt_file(src, dst, passphrase):
    with open(src, "rb") as f:
        data = f.read()
    with open(dst, "w", encoding="utf-8") as f:
        f.write(encrypt_bytes(data, passphrase))


def decrypt_file(src, dst, passphrase):
    with open(src, encoding="utf-8") as f:
        env = f.read()
    data = decrypt_bytes(env, passphrase)
    with open(dst, "wb") as f:
        f.write(data)


def get_passphrase() -> str:
    p = os.environ.get("ASSET_PASSPHRASE")
    if not p:
        p = getpass.getpass("비밀번호: ")
    return p


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in ("encrypt", "decrypt"):
        print(__doc__)
        sys.exit(1)
    mode, src, dst = sys.argv[1:]
    pw = get_passphrase()
    if mode == "encrypt":
        encrypt_file(src, dst, pw)
    else:
        decrypt_file(src, dst, pw)
    print(f"{mode} OK: {src} -> {dst}")
