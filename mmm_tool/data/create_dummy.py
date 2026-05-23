"""Generate dummy MMM dataset for testing."""
import pandas as pd
import numpy as np
from pathlib import Path

np.random.seed(42)

months = pd.date_range("2023-01-01", periods=24, freq="MS")
regions = ["North", "South", "East", "West"]
channels = ["Email", "Social", "Display", "Search", "TV"]

rows = []
for region in regions:
    for month in months:
        # SALES_VALUE is consistent within a (month, region) pair
        sales = int(np.random.randint(50_000, 200_000))
        for channel in channels:
            rows.append(
                {
                    "MONTH_DT": month.strftime("%Y-%m-%d"),
                    "REGION": region,
                    "SALES_VALUE": sales,
                    "INTERACTION_CHANNEL": channel,
                    "NUMBER_OF_INTERACTIONS": int(np.random.randint(1_000, 50_000)),
                }
            )

df = pd.DataFrame(rows)
out = Path(__file__).parent

df.to_csv(out / "dummy_data.csv", index=False)
df.to_excel(out / "dummy_data.xlsx", index=False, engine="openpyxl")
print(f"Created {len(df)} rows → dummy_data.csv & dummy_data.xlsx")
print(df.head(10).to_string(index=False))
