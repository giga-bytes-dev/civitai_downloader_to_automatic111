import argparse
import hashlib
from pathlib import Path

from blake3 import blake3


def toFixed(numObj, digits=0):
    return f"{numObj:.{digits}f}"


def compute_sha256(file_path: str) -> str:
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()


def compute_blake3(file_path: str) -> str:
    hash_blake3 = blake3()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_blake3.update(chunk)
    return hash_blake3.hexdigest()


def main():
    parser = argparse.ArgumentParser(description='File info')
    parser.add_argument('url', type=str)
    args = parser.parse_args()

    file_save = Path(args.url)
    file_size = file_save.stat().st_size
    print(f"file_size bytes = {file_size}")
    print(f"file_size kbytes = {toFixed(round(float(file_size/1024), 9), 9)}")

    # sha256_hash = compute_sha256(str(file_save))
    # print(f"sha256_hash = {sha256_hash}")

    blake3_hash = compute_blake3(str(file_save))
    print(f"blake3_hash = {blake3_hash}")


if __name__ == '__main__':
    main()