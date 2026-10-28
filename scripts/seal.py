"""Krypterar datan så att bara den som har en kod kan läsa den i appen.

GitHub Actions har bara den publika nyckeln (docs/data/pubkey.pem). Den kan kryptera
ny data men aldrig läsa den. Den privata nyckeln ligger i docs/data/keys.json,
krypterad en gång per kod, och låses upp i webbläsaren när någon skriver rätt kod.

Användning:
  python3 scripts/seal.py file <klartext.json> <ut.enc>
  python3 scripts/seal.py snapshots <klartextkatalog> docs/data/snapshots
  python3 scripts/seal.py keygen docs/data      (läser koderna från stdin, en per rad)
"""
import base64, glob, json, os, secrets, sys

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERATIONS = 600_000
PUBKEY = os.path.join(os.path.dirname(__file__), "..", "docs", "data", "pubkey.pem")
b64 = lambda b: base64.b64encode(b).decode()


def seal(plain: bytes, pubkey_pem: bytes) -> dict:
    pub = serialization.load_pem_public_key(pubkey_pem)
    key, iv = AESGCM.generate_key(256), secrets.token_bytes(12)
    wrapped = pub.encrypt(key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    return {"v": 1, "k": b64(wrapped), "iv": b64(iv), "ct": b64(AESGCM(key).encrypt(iv, plain, None))}


def seal_file(src, dst):
    out = seal(open(src, "rb").read(), open(PUBKEY, "rb").read())
    json.dump(out, open(dst, "w"))
    print("Krypterade", src, "->", dst)


def seal_snapshots(src_dir, dst_dir):
    # loggens innehållsförteckning: bara bana, datum och tid, inga odds
    os.makedirs(dst_dir, exist_ok=True)
    idx_path = os.path.join(dst_dir, "files.json")
    idx = json.load(open(idx_path)) if os.path.exists(idx_path) else []
    for f in sorted(glob.glob(os.path.join(src_dir, "*.json"))):
        name = os.path.basename(f)[:-5]
        if name == "index":
            continue
        snap = json.load(open(f))
        seal_file(f, os.path.join(dst_dir, name + ".enc"))
        idx.append({"id": name, **{k: snap[k] for k in ("game", "date", "track", "taken", "minsToStart")}})
    json.dump(idx, open(idx_path, "w"), ensure_ascii=False, indent=0)


def keygen(out_dir):
    codes = [line.strip() for line in sys.stdin if line.strip()]
    if not codes:
        sys.exit("Inga koder på stdin")
    priv = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    pkcs8 = priv.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    entries = []
    for code in codes:
        salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
        kek = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS).derive(code.encode())
        entries.append({"salt": b64(salt), "iter": ITERATIONS, "iv": b64(iv), "wrapped": b64(AESGCM(kek).encrypt(iv, pkcs8, None))})
    secrets.SystemRandom().shuffle(entries)  # ordningen avslöjar inte vilken kod som är vilken
    json.dump({"v": 1, "keys": entries}, open(os.path.join(out_dir, "keys.json"), "w"), indent=1)
    open(os.path.join(out_dir, "pubkey.pem"), "wb").write(priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    print(f"Ny nyckel skapad, upplåsbar med {len(codes)} koder")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "file":
        seal_file(sys.argv[2], sys.argv[3])
    elif cmd == "snapshots":
        seal_snapshots(sys.argv[2], sys.argv[3])
    elif cmd == "keygen":
        keygen(sys.argv[2])
    else:
        sys.exit(__doc__)
