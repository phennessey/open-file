#!/usr/bin/env python3
"""ofa.py: reference inspector and packer for OFA packages (spec 0.1).

Standard library only. Python 3.10 or later; zstd needs Python 3.14
(compression.zstd) and brotli needs the third-party `brotli` module.

    ofa.py ls      PACKAGE           list streams
    ofa.py verify  PACKAGE           check container rules, manifest and digests
    ofa.py cat     PACKAGE STREAM    write a stream's decoded bytes to stdout
    ofa.py pack    SRC_DIR OUTPUT    build a package from a directory

`pack` reads SRC_DIR/ofa.json as a template. For each stream it reads the
file at `path` (or at `source`, then applies `content_encoding`), fills in
`size` and `digest`, and writes a deterministic ZIP.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import struct
import sys
import unicodedata
import zipfile
import zlib
from pathlib import Path

MEDIA_TYPE = "application/vnd.ofa+zip"
SPEC_VERSION = "0.1"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
STREAM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
RESERVED_PREFIXES = ("signatures/", "META-INF/", "_ofa/")
MAX_MANIFEST = 16 * 1024 * 1024
MAX_RATIO = 1000  # decoded/stored limit per content-coding step
ALREADY_COMPRESSED = (
    "image/png", "image/jpeg", "image/webp", "image/avif",
    "application/vnd.apache.parquet", "video/", "audio/",
)


class OfaError(Exception):
    pass


# ---------------------------------------------------------------- content codings

def _zstd():
    try:
        from compression import zstd  # Python 3.14+
        return zstd
    except ImportError:
        return None


def _brotli():
    try:
        import brotli  # type: ignore
        return brotli
    except ImportError:
        return None


def encode(data: bytes, coding: str) -> bytes:
    if coding == "gzip":
        return gzip.compress(data, compresslevel=9, mtime=0)
    if coding == "deflate":
        return zlib.compress(data, 9)
    if coding == "zstd" and _zstd():
        return _zstd().compress(data)
    if coding == "br" and _brotli():
        return _brotli().compress(data)
    raise OfaError(f"cannot apply content coding {coding!r} in this Python")


def decode(data: bytes, coding: str, limit: int) -> bytes:
    if coding == "gzip":
        d = zlib.decompressobj(wbits=31)
    elif coding == "deflate":
        d = zlib.decompressobj()
    elif coding == "zstd":
        z = _zstd()
        if not z:
            raise OfaError("zstd needs Python 3.14 or later")
        d = z.ZstdDecompressor()
        out = d.decompress(data, max_length=limit + 1)
        if len(out) > limit:
            raise OfaError("zstd output exceeds the expansion limit")
        return out
    elif coding == "br":
        b = _brotli()
        if not b:
            raise OfaError("br needs the 'brotli' module")
        out = b.decompress(data)
        if len(out) > limit:
            raise OfaError("brotli output exceeds the expansion limit")
        return out
    else:
        raise OfaError(f"unknown content coding {coding!r}")
    out = d.decompress(data, limit + 1)
    if len(out) > limit:
        raise OfaError(f"{coding} output exceeds the expansion limit")
    return out


# ---------------------------------------------------------------- reading

def _no_duplicates(pairs):
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise OfaError(f"duplicate JSON member {k!r} in manifest")
        obj[k] = v
    return obj


def check_name(name: str) -> str | None:
    if name.startswith("/"):
        return "starts with /"
    if any(seg in (".", "..", "") for seg in name.split("/")):
        return "contains an empty, '.' or '..' segment"
    if re.search(r"[\\:\x00-\x1f]", name):
        return "contains backslash, colon or a control character"
    if unicodedata.normalize("NFC", name) != name:
        return "is not in Unicode NFC"
    if len(name.encode()) > 1024 or any(len(s.encode()) > 255 for s in name.split("/")):
        return "is too long"
    return None


class Package:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.zip = zipfile.ZipFile(self.path)
        self.entries = {i.filename: i for i in self.zip.infolist() if not i.filename.endswith("/")}
        self._check_container()
        self.manifest = self._read_manifest()
        self._check_manifest()

    # -- section 4
    def _check_container(self):
        infos = self.zip.infolist()
        with open(self.path, "rb") as f:
            head = f.read(38 + len(MEDIA_TYPE))
        if head[:4] != b"PK\x03\x04":
            raise OfaError("data before the first local header, or not a ZIP")
        if not infos or infos[0].filename != "mimetype":
            raise OfaError("first entry is not 'mimetype'")
        if head[30:38] != b"mimetype" or head[38:] != MEDIA_TYPE.encode():
            raise OfaError("mimetype entry is missing, compressed, has an extra field, or holds the wrong type")
        if self.zip.read("mimetype") != MEDIA_TYPE.encode():
            raise OfaError("mimetype entry holds the wrong media type")

        seen = {}
        ranges = []
        with open(self.path, "rb") as f:
            for info in infos:
                if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    self.errors.append(f"{info.filename}: compression method {info.compress_type} not allowed")
                if info.flag_bits & 0x1:
                    self.errors.append(f"{info.filename}: encrypted entries are not allowed")
                if info.filename.endswith("/"):
                    continue
                problem = check_name(info.filename)
                if problem:
                    self.errors.append(f"{info.filename!r}: name {problem}")
                key = unicodedata.normalize("NFC", info.filename).casefold()
                if key in seen:
                    self.errors.append(f"{info.filename!r} duplicates {seen[key]!r} after case folding")
                seen[key] = info.filename
                f.seek(info.header_offset + 26)
                n, m = struct.unpack("<HH", f.read(4))
                start = info.header_offset
                end = info.header_offset + 30 + n + m + info.compress_size
                ranges.append((start, end, info.filename))
        ranges.sort()
        for (s1, e1, a), (s2, _e2, b) in zip(ranges, ranges[1:]):
            if s2 < e1:
                self.errors.append(f"entries {a!r} and {b!r} overlap")
        if self.errors:
            raise OfaError("; ".join(self.errors))

    # -- section 5
    def _read_manifest(self) -> dict:
        info = self.entries.get("ofa.json")
        if info is None:
            raise OfaError("no ofa.json manifest")
        if info.file_size > MAX_MANIFEST:
            raise OfaError("manifest larger than 16 MiB")
        raw = self.zip.read(info)
        self.manifest_bytes = raw
        if raw.startswith(b"\xef\xbb\xbf"):
            raise OfaError("manifest starts with a byte order mark")
        try:
            m = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise OfaError(f"manifest is not valid UTF-8 JSON: {e}") from e
        if not isinstance(m, dict):
            raise OfaError("manifest is not a JSON object")
        return m

    def _check_manifest(self):
        m = self.manifest
        version = m.get("ofa")
        if not isinstance(version, str) or not re.match(r"^\d+\.\d+$", version):
            self.errors.append("'ofa' version missing or malformed")
        elif version != SPEC_VERSION:
            self.warnings.append(f"package uses spec {version}; this tool knows {SPEC_VERSION}. Listing only.")
        streams = m.get("streams")
        if not isinstance(streams, list) or not streams:
            self.errors.append("'streams' must be a non-empty array")
            streams = []
        ids, paths = set(), set()
        for i, s in enumerate(streams):
            where = f"streams[{i}]"
            if not isinstance(s, dict):
                self.errors.append(f"{where} is not an object")
                continue
            for key in ("id", "path", "media_type", "size", "digest"):
                if key not in s:
                    self.errors.append(f"{where} lacks '{key}'")
            sid, path = s.get("id"), s.get("path")
            if isinstance(sid, str):
                if not STREAM_ID.match(sid):
                    self.errors.append(f"{where}: bad id {sid!r}")
                if sid in ids:
                    self.errors.append(f"{where}: duplicate id {sid!r}")
                ids.add(sid)
            if isinstance(path, str):
                if path in paths:
                    self.errors.append(f"{where}: duplicate path {path!r}")
                paths.add(path)
                if path in ("mimetype", "ofa.json") or path.startswith(RESERVED_PREFIXES):
                    self.errors.append(f"{where}: path {path!r} is reserved")
                if path not in self.entries:
                    self.errors.append(f"stream {sid!r}: entry {path!r} not found")
            if "digest" in s and not DIGEST.match(str(s["digest"])):
                self.errors.append(f"{where}: digest must be sha256:<64 lowercase hex>")
            if "size" in s and not (isinstance(s["size"], int) and s["size"] >= 0):
                self.errors.append(f"{where}: size must be a non-negative integer")
            sch = s.get("schema")
            if sch is not None:
                given = [k for k in ("stream", "inline", "uri") if k in sch]
                if "type" not in sch or len(given) != 1:
                    self.errors.append(f"{where}: schema needs 'type' and exactly one of stream/inline/uri")
        for s in streams:
            if not isinstance(s, dict):
                continue
            refs = list(s.get("describes", []))
            if isinstance(s.get("schema"), dict) and "stream" in s["schema"]:
                refs.append(s["schema"]["stream"])
            for r in refs:
                if r not in ids:
                    self.errors.append(f"stream {s.get('id')!r} refers to unknown stream {r!r}")
        if "primary" in m and m["primary"] not in ids:
            self.errors.append(f"primary {m['primary']!r} is not a stream id")
        described = paths | {"mimetype", "ofa.json"}
        for name in self.entries:
            if name not in described and not name.startswith("signatures/"):
                self.warnings.append(f"entry {name!r} is not described in the manifest; ignoring it")
        unknown_required = [r for r in m.get("requires", [])]
        if unknown_required:
            self.warnings.append("package requires extensions this tool does not implement: " + ", ".join(unknown_required))

    # -- section 7
    def stream(self, sid: str) -> dict:
        for s in self.manifest.get("streams", []):
            if s.get("id") == sid:
                return s
        raise OfaError(f"no stream with id {sid!r}")

    def stored_bytes(self, s: dict) -> bytes:
        size = s["size"]
        with self.zip.open(s["path"]) as f:
            data = f.read(size + 1)
        if len(data) != size:
            raise OfaError(f"stream {s['id']!r}: size {len(data)} differs from manifest {size}")
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        if digest != s["digest"]:
            raise OfaError(f"stream {s['id']!r}: digest mismatch")
        return data

    def decoded_bytes(self, s: dict) -> bytes:
        data = self.stored_bytes(s)
        for coding in reversed(s.get("content_encoding", [])):
            data = decode(data, coding, max(len(data), 1) * MAX_RATIO)
        return data


# ---------------------------------------------------------------- commands

def cmd_ls(args) -> int:
    pkg = Package(args.package)
    m = pkg.manifest
    print(f"{args.package}  (ofa {m.get('ofa')})")
    if m.get("title"):
        print(f"title: {m['title']}")
    print(f"package digest: sha256:{hashlib.sha256(pkg.manifest_bytes).hexdigest()}")
    rows = [("ID", "ROLE", "MEDIA TYPE", "CODING", "SIZE", "PATH")]
    for s in m.get("streams", []):
        mark = "*" if s.get("id") == m.get("primary") else ""
        rows.append((
            str(s.get("id")) + mark, s.get("role", "data"), s.get("media_type", "?"),
            "+".join(s.get("content_encoding", [])) or "-", str(s.get("size", "?")), s.get("path", "?"),
        ))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip())
    for w in pkg.warnings:
        print(f"warning: {w}", file=sys.stderr)
    for e in pkg.errors:
        print(f"error: {e}", file=sys.stderr)
    return 1 if pkg.errors else 0


def cmd_verify(args) -> int:
    pkg = Package(args.package)
    failures = list(pkg.errors)
    for s in pkg.manifest.get("streams", []):
        try:
            data = pkg.decoded_bytes(s)
            if s.get("media_type", "").split(";")[0].strip() in ("application/json", "application/schema+json"):
                json.loads(data)
        except (OfaError, KeyError, ValueError) as e:
            failures.append(str(e))
    try:
        import jsonschema  # type: ignore
        schema_path = Path(__file__).resolve().parent.parent / "schema" / "ofa-manifest.schema.json"
        jsonschema.validate(pkg.manifest, json.loads(schema_path.read_text()))
    except ImportError:
        pass
    except Exception as e:  # jsonschema.ValidationError
        failures.append(f"manifest schema: {e}")
    for w in pkg.warnings:
        print(f"warning: {w}")
    for f in failures:
        print(f"FAIL: {f}")
    if not failures:
        n = len(pkg.manifest["streams"])
        print(f"OK: {args.package}: {n} streams, all digests match")
    return 1 if failures else 0


def cmd_cat(args) -> int:
    pkg = Package(args.package)
    sys.stdout.buffer.write(pkg.decoded_bytes(pkg.stream(args.stream)))
    return 0


def cmd_pack(args) -> int:
    src = Path(args.src)
    template = json.loads((src / "ofa.json").read_text(encoding="utf-8"))
    template.setdefault("ofa", SPEC_VERSION)
    payloads: list[tuple[str, bytes, bool]] = []
    for s in template["streams"]:
        source = s.pop("source", None)
        data = (src / (source or s["path"])).read_bytes()
        if source:
            for coding in s.get("content_encoding", []):
                data = encode(data, coding)
        s["size"] = len(data)
        s["digest"] = "sha256:" + hashlib.sha256(data).hexdigest()
        mt = s["media_type"].split(";")[0].strip()
        store = bool(s.get("content_encoding")) or mt.startswith(ALREADY_COMPRESSED)
        payloads.append((s["path"], data, store))
    manifest = (json.dumps(template, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    def add(z: zipfile.ZipFile, name: str, data: bytes, store: bool):
        info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
        info.compress_type = zipfile.ZIP_STORED if store else zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        info.create_system = 3
        info.flag_bits |= 0x800  # UTF-8 names
        z.writestr(info, data, compresslevel=9 if not store else None)

    out = Path(args.output)
    with zipfile.ZipFile(out, "w") as z:
        add(z, "mimetype", MEDIA_TYPE.encode(), True)
        add(z, "ofa.json", manifest, False)
        for name, data, store in payloads:
            add(z, name, data, store)
    Package(out)  # re-open to check what we wrote
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(payloads)} streams)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ofa.py", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ls"); a.add_argument("package"); a.set_defaults(fn=cmd_ls)
    a = sub.add_parser("verify"); a.add_argument("package"); a.set_defaults(fn=cmd_verify)
    a = sub.add_parser("cat"); a.add_argument("package"); a.add_argument("stream"); a.set_defaults(fn=cmd_cat)
    a = sub.add_parser("pack"); a.add_argument("src"); a.add_argument("output"); a.set_defaults(fn=cmd_pack)
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except (OfaError, zipfile.BadZipFile) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
