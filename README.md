# Sri Lanka Spatial Economic Analysis Platform

This Streamlit application provides interactive spatial and temporal exploration of Sri Lankan economic estimates aggregated to administrative units.

## Run locally

1. Open PowerShell in the project folder:

```powershell
cd "c:\Users\LENOVO\VS Cord Sl Grid data"
```

2. Create and activate the virtual environment if needed:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```powershell
pip install -r requirements.txt
```

4. Run the app:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

5. Open the app in your browser at:

```text
http://localhost:8501
```

## Deploy on Streamlit Cloud

1. Initialize git and commit the project:

```powershell
git init
git add .
git commit -m "Initial Streamlit spatial economic analysis app"
```

2. Push to a GitHub repository.

3. In Streamlit Cloud, connect the GitHub repo and set the main file to `app.py`.

## Notes

- The app uses `data/processed/spatial_aggregates.gpkg`, `province_yearly.csv`, and `district_yearly.csv`.
- If the repository is too large, you may need to exclude raw dataset files or use Git LFS.
