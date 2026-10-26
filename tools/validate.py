#!/usr/bin/env python3
"""Validate catalog/ against schemas + cross-file rules. Exit 1 on any error."""
import json, sys
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent / "catalog"


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def check(catalog=ROOT, schema_dir=None):
    errs = []
    sd = schema_dir or catalog / "schema"
    schemas = {k: Draft202012Validator(load(sd / f"{k}.schema.json")) for k in ("app", "device")}
    devices, apps = {}, {}
    for kind, d in (("device", "devices"), ("app", "apps")):
        for p in sorted((catalog / d).glob("*.json")):
            doc = load(p)
            errs += [f"{p.name}: {'/'.join(map(str, e.path))}: {e.message}" for e in schemas[kind].iter_errors(doc)]
            if "id" in doc:
                if doc["id"] != p.stem:
                    errs.append(f"{p.name}: id '{doc['id']}' != filename")
                (devices if kind == "device" else apps)[doc["id"]] = doc
    if errs:   # cross-file rules assume schema-valid documents
        return errs
    for a in apps.values():
        for i, art in enumerate(a.get("artifacts", [])):
            w = f"{a['id']}.artifacts[{i}]"
            dev = devices.get(art.get("device"))
            if not dev:
                errs.append(f"{w}: unknown device '{art.get('device')}'")
                continue
            if art.get("firmware") not in dev["firmware"]:
                errs.append(f"{w}: firmware '{art.get('firmware')}' not on device")
            if art.get("format") != dev["package_format"]:
                errs.append(f"{w}: format != device package_format")
            comp = art.get("compatibility", {})
            if art.get("status") == "available":
                for f in ("version", "url", "sha256", "size"):
                    if f not in art:
                        errs.append(f"{w}: available artifact missing '{f}'")
                if a.get("license") == "unknown":
                    errs.append(f"{w}: available artifact with unknown license")
                if comp.get("level") in ("unsupported", "untested"):
                    errs.append(f"{w}: available artifact has level '{comp.get('level')}'")
            else:
                if not art.get("unavailable_reason"):
                    errs.append(f"{w}: unavailable artifact needs unavailable_reason")
                if comp.get("level") == "verified":
                    errs.append(f"{w}: unavailable artifact cannot be verified")
            if comp.get("level") == "verified":
                if not any(e.get("sha256") == art.get("sha256") for e in comp.get("evidence", [])):
                    errs.append(f"{w}: verified needs evidence whose sha256 matches the artifact")
    return errs


if __name__ == "__main__":
    e = check()
    print("\n".join(e) if e else "catalog OK")
    sys.exit(1 if e else 0)
