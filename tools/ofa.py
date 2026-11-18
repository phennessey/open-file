#!/usr/bin/env python3
"""ofa.py: reference inspector and packer for OFA packages (spec 0.2).

Standard library only. Python 3.10 or later; zstd needs Python 3.14
(compression.zstd) and brotli needs the third-party `brotli` module.

    ofa.py ls      PACKAGE             list resources
    ofa.py verify  PACKAGE             check container rules, manifest and hashes
    ofa.py cat     PACKAGE RESOURCE    write a resource's decoded bytes to stdout
    ofa.py pack    SRC_DIR OUTPUT      build a package from a directory

The manifest is a Frictionless Data Package v2 descriptor, datapackage.json,
with OFA's additions in private `_ofa` properties (RFC 0002).

`pack` reads SRC_DIR/datapackage.json as a template. For each resource it
reads the file at `path` (or at `source`, then applies
`_ofa.contentEncoding`), fills in `bytes` and `hash`, and writes a
deterministic ZIP.
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
SPEC_VERSION = "0.2"
MANIFEST = "datapackage.json"
PROFILE = "https://ofa-format.org/profiles/0.2/datapackage.json"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
RESOURCE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
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
        info = self.entries.get(MANIFEST)
        if info is None:
            raise OfaError(f"no {MANIFEST} manifest")
        if len(self.zip.infolist()) < 2 or self.zip.infolist()[1].filename != MANIFEST:
            self.errors.append(f"{MANIFEST} is not the second entry")
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
        resources = m.get("resources")
        if not isinstance(resources, list) or not resources:
            self.errors.append("'resources' must be a non-empty array")
            resources = []
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
            ext = r.get("_ofa", {})
            if not isinstance(ext, dict):
                self.errors.append(f"{where}: '_ofa' must be an object")
                continue
            sch = ext.get("schema")
            if sch is not None:
                given = [k for k in ("resource", "inline", "uri") if k in sch]
                if "type" not in sch or len(given) != 1:
                    self.errors.append(f"{where}: _ofa.schema needs 'type' and exactly one of resource/inline/uri")
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
        size = r["bytes"]
        with self.zip.open(r["path"]) as f:
            data = f.read(size + 1)
        if len(data) != size:
            raise OfaError(f"resource {r['name']!r}: size {len(data)} differs from manifest {size}")
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        if digest != r["hash"]:
            raise OfaError(f"resource {r['name']!r}: hash mismatch")
        return data

    def decoded_bytes(self, r: dict) -> bytes:
        data = self.stored_bytes(r)
        for coding in reversed(r.get("_ofa", {}).get("contentEncoding", [])):
            data = decode(data, coding, max(len(data), 1) * MAX_RATIO)
        return data


# ---------------------------------------------------------------- commands

def cmd_ls(args) -> int:
    pkg = Package(args.package)
    m = pkg.manifest
    print(f"{args.package}  (ofa {m.get('_ofa', {}).get('version')})")
    if m.get("title"):
        print(f"title: {m['title']}")
    print(f"package digest: sha256:{hashlib.sha256(pkg.manifest_bytes).hexdigest()}")
    primary = m.get("_ofa", {}).get("primary")
    rows = [("NAME", "ROLE", "MEDIA TYPE", "CODING", "BYTES", "PATH")]
    for r in m.get("resources", []):
        ext = r.get("_ofa", {})
        mark = "*" if r.get("name") == primary else ""
        rows.append((
            str(r.get("name")) + mark, ext.get("role", "data"), r.get("mediatype", "?"),
            "+".join(ext.get("contentEncoding", [])) or "-", str(r.get("bytes", "?")), r.get("path", "?"),
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
    pkg = Package(args.package)
    sys.stdout.buffer.write(pkg.decoded_bytes(pkg.resource(args.resource)))
    return 0


def cmd_pack(args) -> int:
    src = Path(args.src)
    template = json.loads((src / MANIFEST).read_text(encoding="utf-8"))
    template.setdefault("$schema", PROFILE)
    template.setdefault("_ofa", {}).setdefault("version", SPEC_VERSION)
    payloads: list[tuple[str, bytes, bool]] = []
    for r in template["resources"]:
        source = r.pop("source", None)
        codings = r.get("_ofa", {}).get("contentEncoding", [])
        data = (src / (source or r["path"])).read_bytes()
        if source:
            for coding in codings:
                data = encode(data, coding)
        r["bytes"] = len(data)
        r["hash"] = "sha256:" + hashlib.sha256(data).hexdigest()
        mt = r["mediatype"].split(";")[0].strip()
        store = bool(codings) or mt.startswith(ALREADY_COMPRESSED)
        payloads.append((r["path"], data, store))
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
        add(z, MANIFEST, manifest, False)
        for name, data, store in payloads:
            add(z, name, data, store)
    Package(out)  # re-open to check what we wrote
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(payloads)} resources)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ofa.py", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ls"); a.add_argument("package"); a.set_defaults(fn=cmd_ls)
    a = sub.add_parser("verify"); a.add_argument("package"); a.set_defaults(fn=cmd_verify)
    a = sub.add_parser("cat"); a.add_argument("package"); a.add_argument("resource"); a.set_defaults(fn=cmd_cat)
    a = sub.add_parser("pack"); a.add_argument("src"); a.add_argument("output"); a.set_defaults(fn=cmd_pack)
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except (OfaError, zipfile.BadZipFile) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
