# Hospital Ward Alert Dispatcher (Part C + Part D)

## Important specification note
The handout says “MERN” in Part C, but item 10 explicitly requires a **Flask backend and SQLite database**. This implementation follows the more specific integration requirement: **React + Vite frontend, Flask REST API, SQLite**. It is not a MongoDB/Express MERN backend.

## Project structure
- `backend/app.py` — REST API, validation, five-category classification, routing, handler capacity, status tracking, analytics, SQLite persistence.
- `frontend/` — responsive React interfaces: report submission, user dashboard/search, handler dashboard, routing management, analytics.
- `tests/test_app.py` — 18 automated test cases.

## Run on Windows / VS Code
### 1. Backend
Open terminal in `hospital_ward_dispatcher/backend`:
```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```
Backend runs at `http://127.0.0.1:5000`.

### 2. Frontend
Open a second terminal in `hospital_ward_dispatcher/frontend`:
```powershell
npm install
npm run dev
```
Open the localhost URL printed by Vite (normally `http://localhost:5173`).

## Example valid identifiers
- `WARDAB12-ALERT[CRITICAL]`
- `WARDAB12-ALERT[URGENT]`
- `WARDAB12-ALERT[ROUTINE]`
- `WARDAB12-ALERT[SUPPLY]`
- `WARDAB12-ALERT[MAINTENANCE]`

The identifier grammar implemented is `WARD[ A-Z ][ A-Z ][ 0-9 ][ 0-9 ]-ALERT[CATEGORY]` with no spaces. Replace the two letters and two digits as required.

## Run tests
From the project root:
```powershell
py -m pip install Flask flask-cors
py -m unittest discover -s tests -v
```
The test suite uses a temporary SQLite database and does not overwrite the normal application database.

## Demonstration sequence
1. Start backend and frontend.
2. Submit one report for each of the five categories.
3. Submit an invalid identifier and show the validation message.
4. Open User Dashboard; search using a generated report ID.
5. Open Handler Dashboard; update a handler's availability/capacity and change a report status.
6. Open Routing Management to show the explicit table and queue/assignment decisions.
7. Open Analytics to show category, zone, and status distributions.
8. Run the test suite and show that 18 tests pass.

## Notes
- This is an academic demonstration system, not a production hospital alert platform.
- The routing table and handler names are sample data and should be customized to your teacher's required zones/departments.
- Critical urgency is an override: it is routed to the Nursing Supervisor emergency queue with priority 1.
