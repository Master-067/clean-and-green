# Clean & Green - Simple Working Model

Python Flask + SQLite + HTML/CSS/JavaScript + Leaflet/OpenStreetMap. No Docker, React, PostgreSQL, or separate frontend server.

## Run
python -m venv venv

Windows: `venv\\Scripts\\activate`
Linux/macOS: `source venv/bin/activate`

`pip install -r requirements.txt`
`python app.py`

Open http://127.0.0.1:5000

Demo accounts:
- citizen@example.com / password123
- worker@example.com / password123
- admin@example.com / password123

The admin Live Map shows bin fill levels, vehicle GPS locations, and collection routes. Click **Simulate IoT/GPS Update** to move vehicles and change bin fill levels in real time.
