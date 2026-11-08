"""Compare engine output with hand-worked expected tasks and case times. Task rows only; timers and routes are implied."""
import json, os, sys

def rows(run):
    return sorted([t["case"], t["task"], t["visit"], t["enabled"], t["start"], t["end"], t["resource"], t["service"]] for t in run["tasks"])

def main(expected_path, out_dir):
    exp = json.load(open(expected_path, encoding="utf-8"))
    bad = 0
    for sid, want in exp.items():
        if sid.startswith("_"):
            continue
        if "same_as" in want:
            want = exp[want["same_as"]]
        run = json.load(open(os.path.join(out_dir, sid + ".json"), encoding="utf-8"))
        if run["status"] != "ok":
            print("FAIL", sid, run); bad += 1; continue
        got_t, want_t = rows(run), sorted(want["tasks"])
        got_c = {c["case"]: [c["arrival"], c["end"]] for c in run["cases"]}
        ok = got_t == want_t and got_c == want["cases"]
        print("ok  " if ok else "FAIL", sid)
        if not ok:
            bad += 1
            for r in want_t:
                if r not in got_t: print("   want", r)
            for r in got_t:
                if r not in want_t: print("   got ", r)
            if got_c != want["cases"]: print("   cases want", want["cases"], "got", got_c)
    print("mismatches:", bad)

main(sys.argv[1], sys.argv[2])
