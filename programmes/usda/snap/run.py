#!/usr/bin/env python3
"""Run SNAP cases through both federal and TX overlay programmes."""
from __future__ import annotations

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
BINARY = ROOT / "target" / "debug" / "rac"


def build_request(case: dict, program_yaml: dict) -> dict:
    interval = {"start": str(case["period"]["start"]), "end": str(case["period"]["end"])}
    hh_id = case["household_id"]
    inputs = []
    for name, value in case["household_inputs"].items():
        inputs.append({
            "name": name, "entity": "Household", "entity_id": hh_id,
            "interval": interval, "value": value,
        })
    relations = []
    for m in case["members"]:
        for field in ("earned_income", "unearned_income"):
            inputs.append({
                "name": field, "entity": "Person", "entity_id": m["person_id"],
                "interval": interval,
                "value": {"kind": "decimal", "value": str(m[field])},
            })
        inputs.append({
            "name": "age", "entity": "Person", "entity_id": m["person_id"],
            "interval": interval,
            "value": {"kind": "integer", "value": int(m["age"])},
        })
        relations.append({
            "name": "member_of_household",
            "tuple": [m["person_id"], hh_id],
            "interval": interval,
        })
    return {
        "mode": "explain", "program": program_yaml,
        "dataset": {"inputs": inputs, "relations": relations},
        "queries": [{
            "entity_id": hh_id, "period": case["period"],
            "outputs": ["medical_deduction", "net_income", "snap_allotment", "snap_eligible"],
        }],
    }


def load_merged_program(path: Path) -> dict:
    """Mimic the engine's `extends:` merge so we can pass a single merged
    Program object through the JSON API (which doesn't re-resolve extends)."""
    doc = yaml.safe_load(path.read_text())
    extends = doc.pop("extends", None)
    if not extends:
        return doc
    base = load_merged_program((path.parent / extends).resolve())
    # Concatenate parameter versions; additive for everything else.
    base_params = {p["name"]: p for p in base.get("parameters", [])}
    for p in doc.get("parameters", []):
        if p["name"] in base_params:
            base_params[p["name"]]["versions"].extend(p.get("versions", []))
        else:
            base.setdefault("parameters", []).append(p)
    # Units / relations / derived: additive with duplicate-name errors.
    for kind in ("units", "relations", "derived"):
        existing = {e["name"] for e in base.get(kind, [])}
        for e in doc.get(kind, []):
            if e["name"] in existing:
                raise SystemExit(f"duplicate {kind[:-1]} `{e['name']}` in overlay")
            base.setdefault(kind, []).append(e)
    return base


def run_case(program_path: Path, case: dict) -> dict:
    program = load_merged_program(program_path)
    req = build_request(case, program)
    proc = subprocess.run(
        [str(BINARY)], input=json.dumps(req, default=str),
        capture_output=True, text=True, timeout=15,
    )
    if proc.returncode != 0:
        raise SystemExit(f"engine error: {proc.stderr}")
    return json.loads(proc.stdout)["results"][0]["outputs"]


def fmt_scalar(block: dict) -> str:
    if block.get("kind") == "judgment":
        return block["outcome"]
    v = block["value"]
    return str(v["value"])


def main() -> None:
    cases_doc = yaml.safe_load((HERE / "cases.yaml").read_text())
    programmes = {
        "federal": HERE / "federal" / "program.yaml",
        "us-tx": HERE / "us-tx" / "program.yaml",
    }

    passes, fails = 0, 0
    for case in cases_doc["cases"]:
        print(f"\n=== {case['name']} ===")
        for variant, path in programmes.items():
            outputs = run_case(path, case)
            md = fmt_scalar(outputs["medical_deduction"])
            ni = fmt_scalar(outputs["net_income"])
            al = fmt_scalar(outputs["snap_allotment"])
            eli = fmt_scalar(outputs["snap_eligible"])
            expected_md = case["expected"][variant]["medical_deduction"]
            ok = Decimal(md) == Decimal(expected_md)
            status = "PASS" if ok else "FAIL"
            print(f"  {variant:8s}  medical_deduction={md:>6s}  net_income={ni:>7s}  snap_allotment={al:>4s}  eligible={eli}  [{status}] expected_md={expected_md}")
            if ok:
                passes += 1
            else:
                fails += 1

    print(f"\n{passes} pass / {fails} fail out of {passes + fails} checks")
    sys.exit(0 if fails == 0 else 1)


if __name__ == "__main__":
    main()
