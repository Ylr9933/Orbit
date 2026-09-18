"""Example task input; compilation copies this file but never executes it."""

import csv
import json
import statistics
from pathlib import Path

with Path("data/raw/values.csv").open() as stream:
    values = [float(row["value"]) for row in csv.DictReader(stream)]
output = Path("artifacts/comparison.json")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"mean": statistics.mean(values), "median": statistics.median(values)}))
