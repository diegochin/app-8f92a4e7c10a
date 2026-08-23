import os
import sys
import json
import re
from datetime import datetime, timezone

# Determine Target Year
if len(sys.argv) > 1:
    target_year = sys.argv[1].strip()
else:
    target_year = input("Enter year key (e.g., 2018, 2019, 2020_21, 2022, 2023): ").strip()

js_path = os.path.join("data", f"data-{target_year}.js")
media_folder = target_year

if not os.path.exists(js_path):
    print(f"Error: Could not find {js_path}")
    exit(1)

if not os.path.exists(media_folder):
    print(f"Error: Media folder '{media_folder}/' not found.")
    exit(1)

# 1. Parse tripsData from JS file
with open(js_path, "r", encoding="utf-8") as f:
    js_content = f.read()

start_marker = f"window.journalData_{target_year} = ["
start_idx = js_content.find(start_marker)
if start_idx == -1:
    # Fallback to any array assignment
    start_idx = js_content.find("= [")
    if start_idx == -1:
        print(f"Error: Could not find data array in {js_path}")
        exit(1)
    start_idx += 2
else:
    start_idx += len(start_marker) - 1

bracket_count = 0
end_idx = -1
for i in range(start_idx, len(js_content)):
    if js_content[i] == "[":
        bracket_count += 1
    elif js_content[i] == "]":
        bracket_count -= 1
        if bracket_count == 0:
            end_idx = i + 1
            break

trips = json.loads(js_content[start_idx:end_idx])

# 2. Extract every image/video inside the year folder
media_exts = (".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".m4v")
media_files = [f for f in os.listdir(media_folder) if f.lower().endswith(media_exts)]
entries = []

MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]

for f in media_files:
    full_path = os.path.join(media_folder, f)
    dt = None

    # Method A: Extract date from standard filename (IMG_YYYYMMDD_...)
    match_fn = re.search(r'(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])', f)
    if match_fn:
        try:
            year, month, day = int(match_fn.group(1)), int(match_fn.group(2)), int(match_fn.group(3))
            dt = datetime(year, month, day, tzinfo=timezone.utc)
        except Exception:
            pass

    # Method B: Fallback to JSON metadata timestamp
    if not dt:
        base = os.path.splitext(f)[0]
        possible_jsons = [
            os.path.join(media_folder, f"{f}.supplemental-metadata.json"),
            os.path.join(media_folder, f"{f}.json"),
            os.path.join(media_folder, f"{base}.supplemental-metadata.json"),
            os.path.join(media_folder, f"{base}.json")
        ]
        if "(" in f:
            clean = f.split("(")[0] + os.path.splitext(f)[1]
            possible_jsons.extend([
                os.path.join(media_folder, f"{clean}.supplemental-metadata(1).json"),
                os.path.join(media_folder, f"{clean}.supplemental-metadata.json"),
                os.path.join(media_folder, f"{clean}.json")
            ])
        for jpath in possible_jsons:
            if os.path.exists(jpath):
                try:
                    with open(jpath, "r", encoding="utf-8") as jf:
                        meta = json.load(jf)
                        ts = int(meta.get("photoTakenTime", {}).get("timestamp", 0))
                        if ts > 0:
                            dt = datetime.fromtimestamp(ts, timezone.utc)
                            break
                except Exception:
                    continue

    if not dt:
        dt = datetime.fromtimestamp(int(os.path.getmtime(full_path)), timezone.utc)

    entries.append({
        "file": f,
        "dt": dt,
        "month_num": dt.month,
        "month_name": MONTH_NAMES[dt.month - 1],
        "day": dt.day,
        "year": dt.year
    })

entries.sort(key=lambda x: x["dt"])

# 3. Clear existing photos
flat_flights = []
for trip in trips:
    for flight in trip["flights"]:
        for wp in flight["waypoints"]:
            wp["photos"] = []
        flat_flights.append(flight)

# 4. Strict Day & Month Matching
allocated = 0
unmatched = []

for item in entries:
    matched = False
    for flight in flat_flights:
        f_date = flight.get("date", "").lower()
        if not f_date:
            continue

        has_month = item["month_name"] in f_date
        has_day = re.search(r'\b0?' + str(item["day"]) + r'\b', f_date) is not None

        if has_month and has_day:
            if flight["waypoints"]:
                flight["waypoints"][0]["photos"].append(item["file"])
                matched = True
                allocated += 1
                break
    if not matched:
        unmatched.append(item)

# 5. Fallback for flights without exact day numbers
if unmatched:
    still_unmatched = []
    for item in unmatched:
        matched = False
        candidates = [fl for fl in flat_flights if item["month_name"] in fl.get("date", "").lower()]
        if len(candidates) == 1 and candidates[0]["waypoints"]:
            candidates[0]["waypoints"][0]["photos"].append(item["file"])
            matched = True
            allocated += 1
        else:
            still_unmatched.append(item)

    if still_unmatched:
        print(f"Notice: {len(still_unmatched)} photos did not match any flight dates:")
        for u in still_unmatched[:5]:
            print(f"  - {u['file']} ({u['year']}-{u['month_num']:02d}-{u['day']:02d})")

# 6. Save back to data-<YEAR>.js
new_file_content = f"window.journalData_{target_year} = {json.dumps(trips, indent=2)};\n"
with open(js_path, "w", encoding="utf-8") as f:
    f.write(new_file_content)

print(f"\nSuccess: Allocated {allocated}/{len(entries)} files into {js_path}!")