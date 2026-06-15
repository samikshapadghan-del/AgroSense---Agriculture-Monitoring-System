# Dataset Folder

Use `crop_market_data.csv` for the built-in training command, or pass any CSV path with `--dataset`.

Generate a reproducible demo dataset:

```powershell
python backend\generate_sample_data.py
```

For a real Kaggle dataset, keep at least a crop/commodity column and a market/modal/average price column. Sensor and quality columns are optional but strongly recommended. See the root README for accepted aliases and training commands.
