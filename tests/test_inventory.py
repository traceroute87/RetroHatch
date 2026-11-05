"""Run: python tests/test_inventory.py  (no framework, no network). The one candidate inventory and the snapshot generated from it."""
import copy, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import make_inventory as M

inv = json.loads(M.INV.read_text(encoding="utf-8"))
apps = inv["applications"]
snap_text = M.OUT.read_text(encoding="utf-8")
snap = json.loads(snap_text)["candidates"]

# ---- clean-checkout regeneration: the committed snapshot is exactly what the inventory generates, and the inventory is valid ----
assert M.problems(inv) == [], M.problems(inv)
regen = json.dumps(M.snapshot(inv), ensure_ascii=False, separators=(",", ":")).replace('},{"id"', '},\n{"id"') + "\n"
assert regen == snap_text, "candidates/rg-nano.json is out of date: run python tools/make_inventory.py"

# ---- one application, one entry; ids stable and URL/version independent; no cap ----
ids = [a["id"] for a in apps]
assert len(ids) == len(set(ids)) and all(M.ID.fullmatch(i) for i in ids)
browser = [a for a in apps if a["kind"] != "support"]
assert len(snap) == len(browser) >= 84 and [e["id"] for e in snap] == [a["id"] for a in browser]
assert [e["name"] for e in snap[:10]] == ["j2me-funkey-rgnano", "NanoCraft", "Funkoban", "Cglpsdl1", "picoarch", "XASH3DFS", "meleelight", "SuDokuL", "TriSpace", "KeyCraft"]
assert "wiki-znax" not in ids and "znax" in ids            # the old wiki-/repo-derived ids are gone
big = copy.deepcopy(inv); big["applications"] = [dict(browser[0], id=f"t{i:03d}") for i in range(300)]
assert len(M.snapshot(big)["candidates"]) == 300            # no artificial limit in the generator

# ---- every entry is read-only and UNAPPROVED; audit detail never reaches the device snapshot ----
assert all(e["approval"] == "unapproved" and e["hardware_test"] == "none" for e in snap)
assert not any(k in e for e in snap for k in ("evidence", "sources", "packages", "package_metadata", "metadata_review", "notes", "kind", "status"))
assert len(snap_text) < 117_545, len(snap_text)              # still smaller than the old two-file pair (117,545 bytes)

# ---- applications are deduplicated, not repositories: collection members stay separate, multi-source apps stay one ----
by = {a["id"]: a for a in apps}
sdl2 = [a for a in apps if any(s["url"] == "https://github.com/joyrider3774/funkey_sdl2_games" for s in a["sources"])]
assert sorted(a["id"] for a in sdl2) == ["checkers", "dynamate", "puztrix", "puzzleland", "retrotime", "waternet", "worm"]
assert all(a["status"] == "package-verified" and a["packages"][0]["container"] == "zip" and a["packages"][0]["name"].endswith(".opk") for a in sdl2)
assert sum(e["repo"] == "joyrider3774/funkey_sdl2_games" for e in snap) == 7
assert len(by["funkoban"]["packages"]) >= 2 and sum(s["type"] == "wiki" for s in by["funkoban"]["sources"]) == 1   # one application, release + wiki links
assert len([s for s in by["eduke32"]["sources"] if s["type"] == "repo"]) == 2                                      # one application, two builds in two repositories
assert sum(e["name"] in ("Funkoban", "Cglpsdl1") for e in snap) == 2                                              # the wiki's listing of them merged, not duplicated
assert sum("listing" in e for e in snap) == 46                                                                    # every FunKey wiki listing kept (44 own rows + 2 merged)

# ---- TaraFi: a catalog app (invisible on the device until a signed catalog exists) is also a candidate, deduplicated by source URL, never approved ----
tf = by["tarafi"]; cat_tf = json.loads((ROOT / "catalog" / "apps" / "tarafi.json").read_text(encoding="utf-8"))
assert tf["status"] == "source-only" and not tf["packages"] and tf["category"] == "media" and tf["sources"][0]["url"] == cat_tf["source"]
assert next(e for e in snap if e["id"] == "tarafi")["source"] == cat_tf["source"] and next(e for e in snap if e["id"] == "tarafi")["approval"] == "unapproved"

kc = by["kishmishnano"]; cat_k = json.loads((ROOT / "catalog" / "apps" / "kishmish-nano.json").read_text(encoding="utf-8"))["artifacts"][0]
assert kc["status"] == "listed" and kc["license"] == "MIT" and kc["category"] == "games" and kc["sources"][0]["url"] == "https://github.com/Alialhashemi23/kishmish-nano"
assert (kc["packages"][0]["url"], kc["packages"][0]["sha256"], kc["packages"][0]["size"]) == (cat_k["url"], cat_k["sha256"], cat_k["size"]) and not kc["packages"][0]["signature"]   # copied from the catalog, no format check claimed
ke = next(e for e in snap if e["id"] == "kishmishnano"); assert ke["approval"] == "unapproved" and ke["hardware_test"] == "none" and ke["package"]["signature"] == "" and "sha256" not in ke["package"]

# ---- cores, support files and system add-ons are distinguished; source-only and unverified are labeled ----
kinds = {a["id"]: a["kind"] for a in apps}
assert kinds["gambattesdlretrocore"] == kinds["vicesdlretrocore"] == "core" and kinds["gmenu2x"] == "system"
assert {i for i, k in kinds.items() if k == "support"} == {"databases", "machines", "squashfs"} and not {"databases", "machines", "squashfs"} & {e["id"] for e in snap}
sd = {e["id"]: e["description"] for e in snap}
assert sd["gambattesdlretrocore"].startswith("Emulator core") and sd["gmenu2x"].startswith("System add-on")
for a in apps:
    if a["status"] == "source-only": assert sd[a["id"]].startswith("Source only") and not a["packages"], a["id"]
    if a["status"] == "unverified": assert sd[a["id"]].startswith("Package not inspected"), a["id"]
assert {a["status"] for a in apps} == set(M.STATUS)

# ---- known limitations are recorded ----
lim = {l["id"]: l["note"] for l in inv["known_limits"]}
assert "41921300975" in lim["wiki-index-actions-run"] and "actions/runs/41921300975" in lim["wiki-index-actions-run"] and "collections" in lim

# ---- raw package identities kept from the (git-ignored) crawls: never snapshot data, never applications, never hashed ----
pe = inv["package_evidence"]; col = {c["id"]: c for c in pe["collections"]}
g = col["32blit_funkey"]["members"]
assert len(g) == 43 and len({m[0] for m in g}) == 43 and all(m[2].endswith(".zip") and m[1] > 0 and m[3] > 0 for m in g)
b32 = [a for a in apps if any(s["url"] == col["32blit_funkey"]["source"] for s in a["sources"])]
assert sorted(a["packages"][0]["name"] for a in b32) == sorted(m[0] for m in g) and len(b32) == 43                       # every game is its own application
assert all(a["status"] == "package-verified" and a["license"] == "unknown" and a["category"] == "games" and "sha256" not in a["packages"][0] for a in b32)
assert all((a["packages"][0]["container_name"], a["packages"][0]["container_size"], a["packages"][0]["size"]) == (m[2], m[3], m[1]) for a in b32 for m in g if m[0] == a["packages"][0]["name"])
assert all(a["packages"][0]["url"].endswith("/releases/download/v1.0/" + a["packages"][0]["container_name"]) and a["packages"][0]["mirrors"][0].split("/releases/")[1].startswith("latest/download/") for a in b32)
assert sum(e["repo"] == "joyrider3774/32blit_funkey" for e in snap) == 43 and len(snap) == 129
pc = col["picoarch-cores"]
assert len(pc["members"]) == 29 and sum(m[2] == "squashfs" for m in pc["members"]) == 11 and pc["frontend"][0] == "picoarch.opk" and len(pc["containers"]) == 2
assert len(pe["crawl_only"]["members"]) == 11 and all(m[2].startswith("https://") for m in pe["crawl_only"]["members"])
assert "sha256" not in json.dumps(pe["collections"] + [pe["crawl_only"]])                                              # nothing was hashed: no hash is claimed
assert not any(e["package"]["name"].startswith("picoarch-") for e in snap)                                      # the picoarch cores are not browser entries
assert len(pe["collections"]) == 2 and sum(a["kind"] == "app" and "picoarch" in a["id"] for a in apps) == 1                  # cores stay grouped: one picoarch application

# ---- package identity matches the raw metadata evidence it cites ----
rec = {r["id"]: r for r in json.loads((ROOT / "discovery" / "opk-metadata-evidence.json").read_text(encoding="utf-8"))["records"]}
n_checked = 0
for a in apps:
    mid = a.get("evidence", {}).get("metadata_id")
    if mid:
        assert mid in rec, (a["id"], mid)
        sha = rec[mid]["package"]["sha256"]
        assert a["packages"][0].get("sha256") == sha, a["id"]; n_checked += 1
assert n_checked >= 30

# ---- validation errors are clear ----
def by_id(a, i): return next(x for x in a if x["id"] == i)
def bad(mut):
    c = copy.deepcopy(inv); mut(c["applications"]); return M.problems(c)
assert any("unique" in e for e in bad(lambda a: a[1].update(id=a[0]["id"])))
assert any("unknown status" in e for e in bad(lambda a: a[0].update(status="approved")))
assert any("not https" in e for e in bad(lambda a: a[0]["packages"][0].update(url="http://x.example/a.opk")))
assert any("package-verified needs" in e for e in bad(lambda a: a[0].update(status="listed")))
assert any("category needs" in e for e in bad(lambda a: a[0].update(category="games", category_basis="")))
assert any("UNAPPROVED" in e for e in bad(lambda a: a[0].update(approval="approved")))
assert any("source-only entries have no package" in e for e in bad(lambda a: by_id(a, "fktd").update(packages=[{"name": "x.opk", "url": "https://x.example/x.opk"}])))
assert any("icon file" in e for e in bad(lambda a: a[0].update(icon_file="icons/missing.png")))
print("inventory tests OK")
