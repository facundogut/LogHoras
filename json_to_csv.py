# json_to_csv.py
import sys, json, csv, os

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def ensure_dir(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def iter_issues(data):
    if isinstance(data, dict):
        for k, v in data.items():
            yield k, v
    elif isinstance(data, list):
        for v in data:
            k = v.get("_id") or v.get("id") or ""
            yield k, v
    else:
        raise ValueError("JSON raíz no es dict ni array.")

def main(inp, outp):
    data = load_json(inp)
    ensure_dir(outp)

    fields = [
        "_id","issue_key","issue_id","assignee_id","assignee_name",
        "summary","entered_at","exited_at","worked_hours"
    ]

    rows = []
    for k, issue in iter_issues(data):
        for e in issue.get("entries") or []:
            rows.append({
                "_id": k,
                "issue_key": issue.get("issue_key",""),
                "issue_id": issue.get("issue_id",""),
                "assignee_id": issue.get("assignee_id",""),
                "assignee_name": issue.get("assignee_name",""),
                "summary": issue.get("summary",""),
                "entered_at": e.get("entered_at",""),
                "exited_at": "" if e.get("exited_at") is None else e.get("exited_at",""),
                "worked_hours": e.get("worked_hours",""),
            })

    with open(outp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: json_to_csv.py <input.json> <output.csv>")
        sys.exit(2)
    main(sys.argv[1], sys.argv[2])
