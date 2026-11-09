"""Run: python tests/test_prod_wiring.py  (no framework, no network, no build).
Static checks that production and DEV stay separated: trust keys, state directories, test seams, build recipe. The behavioural checks
are in ui_prod_test.c and ui_signed_test.c (DEV and PRODUCTION runs, test-only keys)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
H = ROOT / "platforms" / "nano" / "ui"


def keys(path):
    t = path.read_text(encoding="utf-8")
    n = int(re.search(r"#define RH_N_TRUSTED_KEYS (\d+)", t).group(1))
    rows = re.findall(r"\{\{?((?:0x[0-9a-fA-F]{2},?)+)\}\}?", t)
    ks = [bytes(int(x, 16) for x in r.rstrip(",").split(",")) for r in rows]
    return n, ks


nd, dev = keys(H / "trusted_keys_dev.h")
npk, prod = keys(H / "trusted_keys_prod.h")
assert nd == 1 and len(dev[0]) == 32
assert npk in (0, 1) and (npk == 0 or (len(prod[0]) == 32 and any(prod[0])))      # placeholder (no key yet) or one real key, never an all-zero "key"
assert npk == 0 or prod[0] != dev[0], "the DEV signing key must never be a production trust key"
pub = ROOT / "catalog" / "production.pub"
if pub.is_file() and npk: assert bytes.fromhex(pub.read_text().strip()) == prod[0]   # the header is what set_prod_key.py made from production.pub

main = (ROOT / "ui" / "rh_ui_main.c").read_text(encoding="utf-8")
NL = chr(10)
region = main[main.index(NL + "#ifdef RH_DEV"):]
dev_part, prod_part = region.split(NL + "#else", 1)[0], region.split(NL + "#else", 1)[1].split(NL + "#endif", 1)[0]     # first #ifdef RH_DEV ... #else ... #endif
assert "trusted_keys_dev.h" in dev_part and "trusted_keys_prod.h" not in dev_part
assert "trusted_keys_prod.h" in prod_part and "trusted_keys_dev.h" not in prod_part and "RH_DEV_STATE_DIR" not in prod_part
body = main.split("int main(", 1)[1]
prod_init = body[body.rindex(NL + "#else"):].split(NL + "#endif", 1)[0]                                      # the production ops block of main() (last #else)
assert "oc.production = 1;" in prod_init and "RH_NANO_STATE_DIR" in prod_init and "RH_DEV" not in prod_init
for seam in ("extra_ca", "mirror_file", "base_url_file"):                                                # DEV test seams: never set by the production program
    assert seam not in prod_init, seam
assert "!preview && !shot" in prod_init or "!preview && !shot" in body                                  # --shot and preview/test data never enable installing
assert 'preview = 1' in body and body.count("rh_ui_set_ops(") >= 2

ops = (ROOT / "ui" / "rh_ops.c").read_text(encoding="utf-8")
assert '".retrohatch"' in ops and '".retrohatch-dev"' in ops and "c->production ? " in ops           # each mode has its own state dir
assert "if (prod) return a->signed_catalog && a->dest_name[0];" in ops                                 # production: signed-catalog origin, no allowlist
assert ops.count("ALLOWED[") >= 2 and "rhprobe" in ops                                                 # DEV allowlist untouched

b = (H / "build-opk.sh").read_text(encoding="utf-8")
prodsec = b.split('if [ "${DEV:-0}" != 1 ]; then', 1)[1].split("fi", 1)[0]
assert "-DRH_DEV" not in prodsec and "rh_ops.c" in prodsec and "rh_source.c" in prodsec          # production links the install path but without the DEV define
assert "-DRH_DEV" in b.split("elif", 1)[1].split("else NAME=RetroHatch", 1)[0]                     # DEV recipe keeps its own define
assert "PRODCAT" in b and "catalog.pkg" in b and "ca-bundle.crt" in b
assert "DEVCAT" in b and b.count("catalog.pkg") >= 2 and "PRODCAT:-" in b                           # a bundled production catalog only when one is supplied; the DEV one is a separate variable
# experimental test installs (unapproved candidates): compiled only into the DEV OPK, never the production one, and never near signing/approval
assert "RH_EXPERIMENTAL" in b.split("elif", 1)[1].split("else NAME=RetroHatch", 1)[0] and "rh_zip.c" in b.split("elif", 1)[1].split("else NAME=RetroHatch", 1)[0]
assert "RH_EXPERIMENTAL" not in prodsec and "rh_zip" not in prodsec and "-lz" not in prodsec          # the production recipe has neither the define, the ZIP code nor zlib
assert "RH_EXPERIMENTAL" not in main and "rh_ops_exp" not in main                                       # the program source never names it: only the DEV recipe can turn it on
assert ops.count("RH_EXPERIMENTAL") == 3 and 'include "rh_ops_exp.inc"' in ops and "if (!prod) { ops.cand_state" in ops   # the only hooks; production never sets them
for f in ("trust.py", "validate.py", "artifact_verify.py", "make_pkg.py", "make_dev_catalog.py"):
    t = (ROOT / "tools" / f).read_text(encoding="utf-8")
    assert "candidates" not in t, f                                                                     # no signing / approval tool reads the candidate snapshot
assert "x-" not in (ROOT / "catalog" / "approvals.json").read_text(encoding="utf-8")                  # no experimental id was ever approved
print("test_prod_wiring: ok")
