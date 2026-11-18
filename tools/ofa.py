#!/usr/bin/env python3
"""ofa.py: reference inspector and packer for OFA packages (spec 0.3).

Standard library only. Python 3.10 or later; zst needs Python 3.14
(compression.zstd) and br needs the third-party `brotli` module.

    ofa.py ls      PACKAGE             list resources
    ofa.py verify  PACKAGE             check container rules, manifest and hashes
    ofa.py cat     PACKAGE RESOURCE    write a resource's decoded bytes to stdout
    ofa.py pack    SRC_DIR OUTPUT      build a package from a directory
    ofa.py adopt   INPUT OUTPUT        turn a zipped Data Package or folder into OFA

PACKAGE may be a local file or an http(s) URL. For a URL the tool reads only
the parts it needs, using HTTP range requests (SPEC section 4.9).

`ls` and `cat` also open plain zipped Data Packages (no `mimetype` entry) in
compatibility mode, with a warning. `verify` rejects them; run `adopt`.

The manifest is a Frictionless Data Package v2 descriptor, datapackage.json,
with OFA's additions in private `_ofa` properties (RFC 0002). Compressed
resources use the Frictionless `compression` property (RFC 0003).

`pack` reads SRC_DIR/datapackage.json as a template. For each resource it
reads the file at `path` (or at `source`, then compresses it as
`compression` says), fills in `bytes` and `hash`, and writes a deterministic
ZIP.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import mimetypes
import re
import struct
import sys
import unicodedata
import urllib.request
import zipfile
import zlib
from pathlib import Path, PurePosixPath

MEDIA_TYPE = "application/vnd.ofa+zip"
SPEC_VERSION = "0.3"
MANIFEST = "datapackage.json"
PROFILE = f"https://ofa-format.org/profiles/{SPEC_VERSION}/datapackage.json"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
RESOURCE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
RESERVED_PREFIXES = ("signatures/", "META-INF/", "_ofa/")
MAX_MANIFEST = 16 * 1024 * 1024
MAX_RATIO = 1000  # decoded/stored size limit for decompression
COMPRESSION_EXT = {"gz": ".gz", "zst": ".zst", "br": ".br"}
ALREADY_COMPRESSED = (
    "image/png", "image/jpeg", "image/webp", "image/avif",
    "application/vnd.apache.parquet", "video/", "audio/",
)


class OfaError(Exception):
    pass


# ---------------------------------------------------------------- HTTP range reads

class HttpRangeFile(io.RawIOBase):
    """A read-only, seekable file over HTTP range requests."""

    def __init__(self, url: str):
        self.url = url
        self.pos = 0
        self.fetched = 0
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "ofa.py"})
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.headers.get("Accept-Ranges", "").lower() != "bytes":
                raise OfaError("server does not support HTTP range requests")
            self.size = int(r.headers["Content-Length"])

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos

    def seek(self, offset, whence=0):
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    READ_AHEAD = 64 * 1024
    _buf_start, _buf = 0, b""

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        n = min(n, self.size - self.pos)
        if n <= 0:
            return b""
        start, end = self.pos, self.pos + n
        if not (self._buf_start <= start and end <= self._buf_start + len(self._buf)):
            want = min(max(n, self.READ_AHEAD), self.size - start)
            req = urllib.request.Request(self.url, headers={
                "Range": f"bytes={start}-{start + want - 1}", "User-Agent": "ofa.py"})
            with urllib.request.urlopen(req, timeout=30) as r:
                if r.status != 206:
                    raise OfaError("server ignored the range request")
                self._buf_start, self._buf = start, r.read()
            self.fetched += len(self._buf)
        data = self._buf[start - self._buf_start:end - self._buf_start]
        self.pos += len(data)
        return data

    def readinto(self, b):
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)


def open_source(src: str):
    if re.match(r"^https?://", src):
        return HttpRangeFile(src)
    return open(src, "rb")


# ---------------------------------------------------------------- compression

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


def compress(data: bytes, method: str) -> bytes:
    if method == "gz":
        return gzip.compress(data, compresslevel=9, mtime=0)
    if method == "zst" and _zstd():
        return _zstd().compress(data)
    if method == "br" and _brotli():
        return _brotli().compress(data)
    raise OfaError(f"cannot apply compression {method!r} in this Python")


def decompress(data: bytes, method: str, limit: int) -> bytes:
    if method == "gz":
        out = zlib.decompressobj(wbits=31).decompress(data, limit + 1)
    elif method == "zst":
        z = _zstd()
        if not z:
            raise OfaError("zst needs Python 3.14 or later")
        out = z.ZstdDecompressor().decompress(data, max_length=limit + 1)
    elif method == "br":
        b = _brotli()
        if not b:
            raise OfaError("br needs the 'brotli' module")
        out = b.decompress(data)
    else:
        raise OfaError(f"unknown compression {method!r}")
    if len(out) > limit:
        raise OfaError(f"{method} output exceeds the expansion limit")
    return out


# ---------------------------------------------------------------- reading

def _no_duplicates(pairs):
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise OfaError(f"duplicate JSON member {k!r} in manifest")
        obj[k] = v
    return obj


def parse_manifest(raw: bytes) -> dict:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise OfaError("manifest starts with a byte order mark")
    try:
        m = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise OfaError(f"manifest is not valid UTF-8 JSON: {e}") from e
    if not isinstance(m, dict):
        raise OfaError("manifest is not a JSON object")
    return m


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


def find_plain_manifest(names: list[str]) -> str:
    """Locate datapackage.json at the root or inside one top-level folder."""
    if MANIFEST in names:
        return ""
    tops = {n.split("/", 1)[0] for n in names if "/" in n}
    roots = [n for n in names if "/" not in n]
    if len(tops) == 1 and not roots:
        top = tops.pop()
        if f"{top}/{MANIFEST}" in names:
            return top + "/"
    raise OfaError("not an OFA package, and no datapackage.json at the root or in a single top-level folder")


class Package:
    """An OFA package, or a plain zipped Data Package in compatibility mode."""

    def __init__(self, src: str | Path, allow_plain: bool = False):
        self.src = str(src)
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.plain = False
        self.prefix = ""
        self.fp = open_source(self.src)
        self.zip = zipfile.ZipFile(self.fp)
        self.entries = {i.filename: i for i in self.zip.infolist() if not i.filename.endswith("/")}
        self._check_container(allow_plain)
        self.manifest = self._read_manifest()
        self._check_manifest()

    # -- section 4
    def _check_container(self, allow_plain: bool):
        infos = self.zip.infolist()
        self.fp.seek(0)
        head = self.fp.read(38 + len(MEDIA_TYPE))
        if head[:4] != b"PK\x03\x04":
            raise OfaError("data before the first local header, or not a ZIP")
        if "mimetype" not in self.entries:
            if not allow_plain:
                raise OfaError("no 'mimetype' entry: this is not an OFA package (try 'adopt')")
            self.plain = True
            self.prefix = find_plain_manifest(list(self.entries))
            self.warnings.append("plain zipped Data Package, not an OFA package; opened in compatibility mode")
        else:
            if infos[0].filename != "mimetype":
                raise OfaError("first entry is not 'mimetype'")
            if head[30:38] != b"mimetype" or head[38:] != MEDIA_TYPE.encode():
                raise OfaError("mimetype entry is compressed, has an extra field, or holds the wrong type")
            if self.zip.read("mimetype") != MEDIA_TYPE.encode():
                raise OfaError("mimetype entry holds the wrong media type")

        seen = {}
        ranges = []
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
            self.fp.seek(info.header_offset + 26)
            n, m = struct.unpack("<HH", self.fp.read(4))
            ranges.append((info.header_offset, info.header_offset + 30 + n + m + info.compress_size, info.filename))
        ranges.sort()
        for (s1, e1, a), (s2, _e2, b) in zip(ranges, ranges[1:]):
            if s2 < e1:
                self.errors.append(f"entries {a!r} and {b!r} overlap")
        if self.errors:
            raise OfaError("; ".join(self.errors))

    # -- section 5
    def _read_manifest(self) -> dict:
        name = self.prefix + MANIFEST
        info = self.entries.get(name)
        if info is None:
            raise OfaError(f"no {MANIFEST} manifest")
        if not self.plain:
            infos = self.zip.infolist()
            if len(infos) < 2 or infos[1].filename != MANIFEST:
                self.errors.append(f"{MANIFEST} is not the second entry")
        if info.file_size > MAX_MANIFEST:
            raise OfaError("manifest larger than 16 MiB")
        self.manifest_bytes = self.zip.read(info)
        return parse_manifest(self.manifest_bytes)

    def _check_manifest(self):
        m = self.manifest
        resources = m.get("resources")
        if not isinstance(resources, list) or not resources:
            self.errors.append("'resources' must be a non-empty array")
            resources = []
        if self.plain:
            return  # compatibility mode: list and extract only
        if "$schema" not in m:
            self.errors.append("'$schema' missing; it must name the OFA profile")
        elif m["$schema"] != PROFILE:
            self.warnings.append(f"'$schema' is {m['$schema']!r}; this tool knows {PROFILE}")
        ofa = m.get("_ofa")
        if not isinstance(ofa, dict):
            self.errors.append("'_ofa' object missing")
            ofa = {}
        version = ofa.get("version")
        if not isinstance(version, str) or not re.match(r"^\d+\.\d+$", version):
            self.errors.append("'_ofa.version' missing or malformed")
        elif version != SPEC_VERSION:
            self.warnings.append(f"package uses spec {version}; this tool knows {SPEC_VERSION}. Listing only.")
        names, paths = set(), set()
        for i, r in enumerate(resources):
            where = f"resources[{i}]"
            if not isinstance(r, dict):
                self.errors.append(f"{where} is not an object")
                continue
            for key in ("name", "path", "mediatype", "bytes", "hash"):
                if key not in r:
                    self.errors.append(f"{where} lacks '{key}'")
            if "data" in r:
                self.errors.append(f"{where}: inline 'data' is not allowed; every resource is a ZIP entry")
            name, path = r.get("name"), r.get("path")
            if isinstance(name, str):
                if not RESOURCE_NAME.match(name):
                    self.errors.append(f"{where}: bad name {name!r}")
                if name in names:
                    self.errors.append(f"{where}: duplicate name {name!r}")
                names.add(name)
            if "path" in r and not isinstance(path, str):
                self.errors.append(f"{where}: 'path' must be a single string")
            if isinstance(path, str):
                if "://" in path:
                    self.errors.append(f"{where}: 'path' must not be a URL")
                if any(seg.startswith(".") for seg in path.split("/")):
                    self.errors.append(f"{where}: 'path' must not use hidden folders, '.' or '..'")
                if path in paths:
                    self.errors.append(f"{where}: duplicate path {path!r}")
                paths.add(path)
                if path in ("mimetype", MANIFEST) or path.startswith(RESERVED_PREFIXES):
                    self.errors.append(f"{where}: path {path!r} is reserved")
                if path not in self.entries:
                    self.errors.append(f"resource {name!r}: entry {path!r} not found")
            if "hash" in r and not DIGEST.match(str(r["hash"])):
                self.errors.append(f"{where}: hash must be sha256:<64 lowercase hex>")
            if "bytes" in r and not (isinstance(r["bytes"], int) and r["bytes"] >= 0):
                self.errors.append(f"{where}: bytes must be a non-negative integer")
            comp = r.get("compression")
            if comp is not None:
                if comp not in COMPRESSION_EXT:
                    self.errors.append(f"{where}: compression {comp!r} not allowed; use gz, zst or br")
                elif isinstance(path, str) and not path.endswith(COMPRESSION_EXT[comp]):
                    self.errors.append(f"{where}: path must end with {COMPRESSION_EXT[comp]!r} to match compression")
            ext = r.get("_ofa", {})
            if not isinstance(ext, dict):
                self.errors.append(f"{where}: '_ofa' must be an object")
                continue
            if "contentEncoding" in ext:
                self.errors.append(f"{where}: _ofa.contentEncoding was replaced by 'compression' in 0.3")
            sch = ext.get("schema")
            if sch is not None:
                given = [k for k in ("resource", "inline", "uri") if k in sch]
                if "type" not in sch or len(given) != 1:
                    self.errors.append(f"{where}: _ofa.schema needs 'type' and exactly one of resource/inline/uri")
                if "schema" in r:
                    self.errors.append(f"{where}: use either 'schema' or '_ofa.schema', not both")
        for r in resources:
            if not isinstance(r, dict) or not isinstance(r.get("_ofa", {}), dict):
                continue
            ext = r.get("_ofa", {})
            refs = list(ext.get("describes", []))
            if isinstance(ext.get("schema"), dict) and "resource" in ext["schema"]:
                refs.append(ext["schema"]["resource"])
            for ref in refs:
                if ref not in names:
                    self.errors.append(f"resource {r.get('name')!r} refers to unknown resource {ref!r}")
            native = r.get("schema")
            if isinstance(native, str) and native not in paths:
                self.errors.append(f"resource {r.get('name')!r}: schema {native!r} is not a resource path in the package")
        if "primary" in ofa and ofa["primary"] not in names:
            self.errors.append(f"_ofa.primary {ofa['primary']!r} is not a resource name")
        described = paths | {"mimetype", MANIFEST}
        for entry in self.entries:
            if entry not in described and not entry.startswith(("signatures/", "META-INF/")):
                self.warnings.append(f"entry {entry!r} is not described in the manifest; ignoring it")
        unknown_required = list(ofa.get("requires", []))
        if unknown_required:
            self.warnings.append("package requires extensions this tool does not implement: " + ", ".join(unknown_required))

    # -- section 7
    def resource(self, name: str) -> dict:
        for r in self.manifest.get("resources", []):
            if r.get("name") == name:
                return r
        raise OfaError(f"no resource named {name!r}")

    def stored_bytes(self, r: dict) -> bytes:
        path = r.get("path")
        if not isinstance(path, str) or "://" in path:
            raise OfaError(f"resource {r.get('name')!r} is not a single file inside the package")
        entry = self.prefix + path
        if entry not in self.entries:
            raise OfaError(f"resource {r.get('name')!r}: entry {entry!r} not found")
        size = r.get("bytes")
        with self.zip.open(entry) as f:
            data = f.read() if size is None else f.read(size + 1)
        if size is not None and len(data) != size:
            raise OfaError(f"resource {r['name']!r}: size {len(data)} differs from manifest {size}")
        if DIGEST.match(str(r.get("hash", ""))):
            if "sha256:" + hashlib.sha256(data).hexdigest() != r["hash"]:
                raise OfaError(f"resource {r['name']!r}: hash mismatch")
        elif not self.plain:
            raise OfaError(f"resource {r['name']!r}: no SHA-256 hash")
        return data

    def decoded_bytes(self, r: dict) -> bytes:
        data = self.stored_bytes(r)
        comp = r.get("compression")
        if comp:
            data = decompress(data, comp, max(len(data), 1) * MAX_RATIO)
        return data


# ---------------------------------------------------------------- writing

def write_package(out: Path, manifest: dict, payloads: list[tuple[str, bytes]]) -> None:
    """Write mimetype, datapackage.json and payloads as a deterministic ZIP."""
    by_path = {r["path"]: r for r in manifest["resources"]}

    def add(z: zipfile.ZipFile, name: str, data: bytes, store: bool):
        info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
        info.compress_type = zipfile.ZIP_STORED if store else zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        info.create_system = 3
        info.flag_bits |= 0x800  # UTF-8 names
        z.writestr(info, data, compresslevel=9 if not store else None)

    raw = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    with zipfile.ZipFile(out, "w") as z:
        add(z, "mimetype", MEDIA_TYPE.encode(), True)
        add(z, MANIFEST, raw, False)
        for path, data in payloads:
            r = by_path[path]
            mt = r["mediatype"].split(";")[0].strip()
            add(z, path, data, bool(r.get("compression")) or mt.startswith(ALREADY_COMPRESSED))


def describe(r: dict, data: bytes) -> None:
    r["bytes"] = len(data)
    r["hash"] = "sha256:" + hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- commands

def cmd_ls(args) -> int:
    pkg = Package(args.package, allow_plain=True)
    m = pkg.manifest
    label = "plain Data Package" if pkg.plain else f"ofa {m.get('_ofa', {}).get('version')}"
    print(f"{args.package}  ({label})")
    if m.get("title"):
        print(f"title: {m['title']}")
    if not pkg.plain:
        print(f"package digest: sha256:{hashlib.sha256(pkg.manifest_bytes).hexdigest()}")
    primary = m.get("_ofa", {}).get("primary") if isinstance(m.get("_ofa"), dict) else None
    rows = [("NAME", "ROLE", "MEDIA TYPE", "COMPRESSION", "BYTES", "PATH")]
    for r in m.get("resources", []):
        ext = r.get("_ofa", {}) if isinstance(r.get("_ofa"), dict) else {}
        mark = "*" if r.get("name") == primary else ""
        rows.append((
            str(r.get("name")) + mark, ext.get("role", "data"), str(r.get("mediatype", "?")),
            str(r.get("compression", "-")), str(r.get("bytes", "?")), str(r.get("path", "?")),
        ))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip())
    if isinstance(pkg.fp, HttpRangeFile):
        print(f"fetched {pkg.fp.fetched} of {pkg.fp.size} bytes over HTTP", file=sys.stderr)
    for w in pkg.warnings:
        print(f"warning: {w}", file=sys.stderr)
    for e in pkg.errors:
        print(f"error: {e}", file=sys.stderr)
    return 1 if pkg.errors else 0


def cmd_verify(args) -> int:
    pkg = Package(args.package)
    failures = list(pkg.errors)
    for r in pkg.manifest.get("resources", []):
        try:
            data = pkg.decoded_bytes(r)
            if r.get("mediatype", "").split(";")[0].strip() in ("application/json", "application/schema+json"):
                json.loads(data)
        except (OfaError, KeyError, ValueError) as e:
            failures.append(str(e))
    try:
        import jsonschema  # type: ignore
        # Validate the OFA rules only. The profile also references the Data
        # Package v2 profile by URL, and this tool never fetches URLs.
        profile = json.loads((Path(__file__).resolve().parent.parent / "profiles" / SPEC_VERSION / MANIFEST).read_text())
        jsonschema.validate(pkg.manifest, {"$ref": "#/definitions/ofa", "definitions": profile["definitions"]})
    except ImportError:
        pass
    except Exception as e:  # jsonschema.ValidationError
        failures.append(f"manifest schema: {e}")
    for w in pkg.warnings:
        print(f"warning: {w}")
    for f in failures:
        print(f"FAIL: {f}")
    if not failures:
        n = len(pkg.manifest["resources"])
        print(f"OK: {args.package}: {n} resources, all hashes match")
    return 1 if failures else 0


def cmd_cat(args) -> int:
    pkg = Package(args.package, allow_plain=True)
    for w in pkg.warnings:
        print(f"warning: {w}", file=sys.stderr)
    sys.stdout.buffer.write(pkg.decoded_bytes(pkg.resource(args.resource)))
    return 0


def cmd_pack(args) -> int:
    src = Path(args.src)
    template = json.loads((src / MANIFEST).read_text(encoding="utf-8"))
    template.setdefault("$schema", PROFILE)
    template.setdefault("_ofa", {}).setdefault("version", SPEC_VERSION)
    payloads = []
    for r in template["resources"]:
        source = r.pop("source", None)
        data = (src / (source or r["path"])).read_bytes()
        if source and r.get("compression"):
            data = compress(data, r["compression"])
        describe(r, data)
        payloads.append((r["path"], data))
    out = Path(args.output)
    write_package(out, template, payloads)
    Package(out)  # re-open to check what we wrote
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(payloads)} resources)")
    return 0


GUESSED_ROLES = (
    (re.compile(r"^readme(\.|$)", re.I), "documentation"),
    (re.compile(r"^(license|licence|copying)(\.|$)", re.I), "license"),
)
EXTRA_TYPES = {".md": "text/markdown", ".ndjson": "application/x-ndjson", ".jsonl": "application/x-ndjson",
               ".parquet": "application/vnd.apache.parquet", ".yaml": "application/yaml", ".yml": "application/yaml"}


def guess_mediatype(path: str) -> str:
    p = PurePosixPath(path)
    suffix = p.suffix.lower()
    if suffix in COMPRESSION_EXT.values():
        suffix = PurePosixPath(p.stem).suffix.lower()
    return EXTRA_TYPES.get(suffix) or mimetypes.guess_type("x" + suffix)[0] or "application/octet-stream"


def slug(path: str, taken: set) -> str:
    p = PurePosixPath(path)
    stem = p.name[: -len("".join(p.suffixes))] if p.suffixes and p.name != "".join(p.suffixes) else p.name
    base = re.sub(r"[^a-z0-9._-]+", "-", stem.lower()).strip("-.")
    base = re.sub(r"^[^a-z0-9]+", "", base) or "file"
    name, n = base[:120], 2
    while name in taken:
        name, n = f"{base[:115]}-{n}", n + 1
    taken.add(name)
    return name


def cmd_adopt(args) -> int:
    src = Path(args.input)
    files: dict[str, bytes] = {}
    if src.is_dir():
        for f in sorted(src.rglob("*")):
            rel = f.relative_to(src).as_posix()
            if f.is_file() and not any(s.startswith(".") for s in rel.split("/")):
                files[rel] = f.read_bytes()
    else:
        with zipfile.ZipFile(src) as z:
            names = [i.filename for i in z.infolist() if not i.filename.endswith("/")]
            prefix = find_plain_manifest(names) if "mimetype" not in names else ""
            for n in names:
                if n.startswith(prefix):
                    files[n[len(prefix):]] = z.read(n)
    for n in files:
        if check_name(n):
            raise OfaError(f"cannot adopt entry {n!r}: name {check_name(n)}")
    if MANIFEST not in files:
        raise OfaError(f"no {MANIFEST} found to adopt")
    m = parse_manifest(files.pop(MANIFEST))
    files.pop("mimetype", None)
    resources = m.get("resources")
    if not isinstance(resources, list) or not resources:
        raise OfaError("the descriptor has no resources")
    taken = {r.get("name") for r in resources if isinstance(r, dict)}
    used, payloads, notes = set(), [], []
    for r in resources:
        name = r.get("name")
        if "data" in r:
            raise OfaError(f"resource {name!r} uses inline 'data'; move it to a file first")
        path = r.get("path")
        if not isinstance(path, str):
            raise OfaError(f"resource {name!r} has a multipart 'path' array, which OFA cannot carry")
        if "://" in path:
            raise OfaError(f"resource {name!r} points at a URL ({path}); download it into the folder first")
        if path not in files:
            raise OfaError(f"resource {name!r}: file {path!r} not found")
        if not (isinstance(name, str) and RESOURCE_NAME.match(name)):
            raise OfaError(f"resource name {name!r} does not match ^[a-z0-9][a-z0-9._-]*$; rename it first")
        r.setdefault("mediatype", guess_mediatype(path))
        describe(r, files[path])
        payloads.append((path, files[path]))
        used.add(path)
    for path in sorted(set(files) - used):
        if path.startswith(("signatures/", "META-INF/")):
            continue
        r = {"name": slug(path, taken), "path": path, "mediatype": guess_mediatype(path)}
        for pattern, role in GUESSED_ROLES:
            if pattern.match(PurePosixPath(path).name):
                r["_ofa"] = {"role": role}
                if not PurePosixPath(path).suffix:
                    r["mediatype"] = "text/plain"
        describe(r, files[path])
        resources.append(r)
        payloads.append((path, files[path]))
        notes.append(f"described {path!r} as {r['name']!r} ({r['mediatype']}"
                     + (f", role {r['_ofa']['role']}" if "_ofa" in r else "") + ")")
    m = {"$schema": PROFILE, **{k: v for k, v in m.items() if k != "$schema"}}
    m.setdefault("_ofa", {})
    if not isinstance(m["_ofa"], dict):
        raise OfaError("'_ofa' in the descriptor is not an object")
    m["_ofa"]["version"] = SPEC_VERSION
    out = Path(args.output)
    write_package(out, m, payloads)
    pkg = Package(out)
    for n in notes:
        print(f"adopt: {n}")
    for w in pkg.warnings:
        print(f"warning: {w}")
    if pkg.errors:
        for e in pkg.errors:
            print(f"error: {e}")
        return 1
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(payloads)} resources)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ofa.py", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ls"); a.add_argument("package"); a.set_defaults(fn=cmd_ls)
    a = sub.add_parser("verify"); a.add_argument("package"); a.set_defaults(fn=cmd_verify)
    a = sub.add_parser("cat"); a.add_argument("package"); a.add_argument("resource"); a.set_defaults(fn=cmd_cat)
    a = sub.add_parser("pack"); a.add_argument("src"); a.add_argument("output"); a.set_defaults(fn=cmd_pack)
    a = sub.add_parser("adopt"); a.add_argument("input"); a.add_argument("output"); a.set_defaults(fn=cmd_adopt)
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except (OfaError, zipfile.BadZipFile, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
