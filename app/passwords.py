import base64
import getpass
import hashlib
import hmac
import secrets
import sys

N, R, P = 16384, 8, 1
SALT_BYTES = 16
DKLEN = 64


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=DKLEN)
    salt_b64 = base64.b64encode(salt).decode()
    digest_b64 = base64.b64encode(digest).decode()
    return f"scrypt${N}${R}${P}${salt_b64}${digest_b64}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_b64, digest_b64 = encoded.split("$")
        if algorithm != "scrypt":
            return False
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(digest_b64, validate=True)
        digest = hashlib.scrypt(
            password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=DKLEN
        )
    # 字段数不对、base64 无效、参数非法时 hashlib 抛 ValueError 或 TypeError
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)


if __name__ == "__main__":
    password = getpass.getpass("密码：")
    if not password:
        print("密码不能为空", file=sys.stderr)
        sys.exit(1)
    if password != getpass.getpass("再输入一次："):
        print("两次输入的密码不一致", file=sys.stderr)
        sys.exit(1)
    print(hash_password(password))
