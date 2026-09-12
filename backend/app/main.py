from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
UPLOAD_DIR = ROOT / "uploads"
DATA_DIR = ROOT / "data"
UPLOAD_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

app = FastAPI(title="AI Data Analyst Agent", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

META_FILE = DATA_DIR / "datasets.json"
HISTORY_FILE = DATA_DIR / "history.json"


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def save_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, default=str))


def datasets():
    return load_json(META_FILE, [])


def history():
    return load_json(HISTORY_FILE, [])


def table_name(dataset_id: str) -> str:
    return "dataset_" + re.sub(r"[^a-zA-Z0-9_]", "", dataset_id)


def safe_identifier(name: str) -> str:
    # DuckDB quotes column names, so we only need to prevent SQL injection in generated identifiers.
    return '"' + name.replace('"', '""') + '"'


def sql_read_only(sql: str) -> bool:
    cleaned = re.sub(r"--.*?$|/\*.*?\*/", "", sql, flags=re.MULTILINE | re.DOTALL).strip().lower()
    if not cleaned.startswith("select") and not cleaned.startswith("with"):
        return False
    forbidden = r"\b(insert|update|delete|drop|alter|create|copy|attach|detach|install|load|pragma|call|export|import|vacuum)\b"
    return not re.search(forbidden, cleaned)


def execute_sql(dataset_id: str, sql: str) -> pd.DataFrame:
    if not sql_read_only(sql):
        raise HTTPException(400, "Only read-only SELECT/WITH SQL is allowed.")
    db_path = DATA_DIR / f"{dataset_id}.duckdb"
    if not db_path.exists():
        raise HTTPException(404, "Dataset not found")
    con = duckdb.connect(str(db_path), read_only=False)
    try:
        return con.execute(sql).fetchdf()
    except Exception as exc:
        raise HTTPException(400, f"SQL error: {exc}") from exc
    finally:
        con.close()


def normalize_records(df: pd.DataFrame, limit: int = 500):
    out = df.head(limit).copy()
    out = out.where(pd.notnull(out), None)
    return out.to_dict(orient="records")


def dataset_by_id(dataset_id: str):
    for d in datasets():
        if d["id"] == dataset_id:
            return d
    raise HTTPException(404, "Dataset not found")


def infer_types(df: pd.DataFrame):
    cols = []
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s):
            kind = "number"
        elif pd.api.types.is_datetime64_any_dtype(s):
            kind = "date"
        else:
            kind = "text"
        cols.append({"name": str(c), "type": kind, "nulls": int(s.isna().sum())})
    return cols


def heuristic_plan(question: str, meta: dict) -> dict:
    q = question.lower().strip()
    cols = meta["columns"]
    num_cols = [c["name"] for c in cols if c["type"] == "number"]
    text_cols = [c["name"] for c in cols if c["type"] == "text"]
    date_cols = [c["name"] for c in cols if c["type"] == "date"]
    table = safe_identifier(table_name(meta["id"]))

    def find_col(words, candidates):
        for w in words:
            for c in candidates:
                if w in c.lower():
                    return c
        return candidates[0] if candidates else None

    metric = find_col(["revenue", "sales", "amount", "price", "profit", "score", "runs", "value", "total"], num_cols)
    group = find_col(["category", "product", "team", "venue", "city", "region", "department", "customer", "batting", "opponent"], text_cols)
    date_col = find_col(["date", "month", "year", "time"], date_cols + text_cols)
    wants_count = any(x in q for x in ["how many", "count", "number of", "records"])
    wants_avg = any(x in q for x in ["average", "avg", "mean"])
    wants_max = any(x in q for x in ["highest", "maximum", "max", "top"])
    wants_min = any(x in q for x in ["lowest", "minimum", "min"])
    wants_by = any(x in q for x in ["by ", "per ", "each ", "breakdown", "grouped"])
    chart = "bar"

    if wants_count:
        agg = "COUNT(*) AS count"
        answer = "Counted the matching rows in your dataset."
    elif metric and wants_avg:
        agg = f"AVG({safe_identifier(metric)}) AS average_{re.sub(r'[^a-z0-9]+','_',metric.lower()).strip('_')}"
        answer = f"Calculated the average of {metric}."
    elif metric and (wants_max or wants_min):
        fn = "MAX" if wants_max else "MIN"
        agg = f"{fn}({safe_identifier(metric)}) AS {fn.lower()}_{re.sub(r'[^a-z0-9]+','_',metric.lower()).strip('_')}"
        answer = f"Found the {fn.lower()} value of {metric}."
    elif metric:
        agg = f"SUM({safe_identifier(metric)}) AS total_{re.sub(r'[^a-z0-9]+','_',metric.lower()).strip('_')}"
        answer = f"Calculated the total of {metric}."
    else:
        agg = "COUNT(*) AS count"
        answer = "Counted rows because no obvious numeric measure was detected."

    if group and (wants_by or any(k in q for k in group.lower().split())):
        sql = f"SELECT {safe_identifier(group)} AS category, {agg} FROM {table} GROUP BY 1 ORDER BY 2 DESC LIMIT 25"
        chart = "bar"
    elif date_col and any(x in q for x in ["trend", "over time", "monthly", "daily", "timeline"]):
        sql = f"SELECT CAST({safe_identifier(date_col)} AS DATE) AS date, {agg} FROM {table} GROUP BY 1 ORDER BY 1 LIMIT 100"
        chart = "line"
    else:
        sql = f"SELECT {agg} FROM {table}"
        chart = "kpi"
    return {"sql": sql, "chart": chart, "answer": answer, "engine": "heuristic"}


def openai_plan(question: str, meta: dict) -> dict | None:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        schema = "\n".join(f"- {c['name']} ({c['type']})" for c in meta["columns"])
        prompt = f"""You are a safe analytics SQL planner. Dataset table is {table_name(meta['id'])}.\nSchema:\n{schema}\nUser question: {question}\nReturn JSON only with keys sql, chart, answer. SQL must be DuckDB SELECT/WITH only, no mutations. chart must be one of bar,line,kpi,table,pie. Keep SQL concise and reference only the provided table/columns."""
        r = client.chat.completions.create(model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), messages=[{"role":"user","content":prompt}], temperature=0)
        data = json.loads(r.choices[0].message.content)
        if not sql_read_only(data.get("sql", "")):
            return None
        return {"sql": data["sql"], "chart": data.get("chart", "table"), "answer": data.get("answer", "Analysis complete."), "engine": "openai"}
    except Exception:
        return None


class AnalyzeRequest(BaseModel):
    dataset_id: str
    question: str = Field(min_length=2, max_length=1000)


class SQLRequest(BaseModel):
    dataset_id: str
    sql: str = Field(min_length=6, max_length=10000)


class DBConnectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    connection_string: str = Field(min_length=5, max_length=1000)


@app.get("/api/health")
def health():
    return {"status": "ok", "ai_enabled": bool(os.getenv("OPENAI_API_KEY"))}


@app.get("/api/datasets")
def list_datasets():
    return datasets()


@app.post("/api/demo")
def create_demo():
    demo_id = "demo_sales"
    path = UPLOAD_DIR / f"{demo_id}.csv"
    if not path.exists():
        rows = []
        products = ["Laptop", "Phone", "Headphones", "Monitor", "Keyboard"]
        regions = ["North", "South", "East", "West"]
        for i in range(1, 201):
            d = pd.Timestamp("2025-01-01") + pd.Timedelta(days=i % 180)
            p = products[i % len(products)]
            price = {"Laptop": 65000, "Phone": 28000, "Headphones": 3500, "Monitor": 15000, "Keyboard": 1800}[p]
            qty = (i * 7) % 10 + 1
            rows.append({"date": d.date().isoformat(), "product": p, "region": regions[i % 4], "quantity": qty, "revenue": price * qty, "profit": int(price * qty * 0.18)})
        pd.DataFrame(rows).to_csv(path, index=False)
    return ingest_csv(path, display_name="Demo Sales Dataset", forced_id=demo_id)


def ingest_csv(path: Path, display_name: str | None = None, forced_id: str | None = None):
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        raise HTTPException(400, f"Could not read CSV: {exc}") from exc
    if df.empty:
        raise HTTPException(400, "CSV is empty")
    df.columns = [str(c).strip() for c in df.columns]
    # Conservative datetime inference for common date/time columns.
    for c in list(df.columns):
        if any(k in c.lower() for k in ["date", "timestamp", "datetime"]):
            try:
                parsed = pd.to_datetime(df[c], errors="coerce")
                if parsed.notna().mean() > 0.7:
                    df[c] = parsed
            except Exception:
                pass
    dataset_id = forced_id or uuid.uuid4().hex[:10]
    db_path = DATA_DIR / f"{dataset_id}.duckdb"
    con = duckdb.connect(str(db_path))
    con.register("incoming_df", df)
    con.execute(f"CREATE OR REPLACE TABLE {safe_identifier(table_name(dataset_id))} AS SELECT * FROM incoming_df")
    con.unregister("incoming_df")
    con.close()
    meta = {
        "id": dataset_id,
        "name": display_name or path.name,
        "rows": int(len(df)),
        "columns_count": int(len(df.columns)),
        "columns": infer_types(df),
        "source": "csv",
    }
    items = [x for x in datasets() if x["id"] != dataset_id]
    items.insert(0, meta)
    save_json(META_FILE, items)
    return meta


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a CSV file.")
    dataset_id = uuid.uuid4().hex[:10]
    path = UPLOAD_DIR / f"{dataset_id}.csv"
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "CSV must be 25 MB or smaller for the demo deployment.")
    path.write_bytes(data)
    return ingest_csv(path)


@app.get("/api/datasets/{dataset_id}/preview")
def preview(dataset_id: str, limit: int = 25):
    meta = dataset_by_id(dataset_id)
    table = safe_identifier(table_name(dataset_id))
    df = execute_sql(dataset_id, f"SELECT * FROM {table} LIMIT {max(1, min(limit, 100))}")
    return {"dataset": meta, "rows": normalize_records(df, 100)}


@app.get("/api/datasets/{dataset_id}/schema")
def schema(dataset_id: str):
    meta = dataset_by_id(dataset_id)
    return meta


@app.post("/api/sql")
def run_sql(req: SQLRequest):
    dataset_by_id(req.dataset_id)
    df = execute_sql(req.dataset_id, req.sql)
    return {"columns": list(df.columns), "rows": normalize_records(df), "row_count": int(len(df))}


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    meta = dataset_by_id(req.dataset_id)
    plan = openai_plan(req.question, meta) or heuristic_plan(req.question, meta)
    df = execute_sql(req.dataset_id, plan["sql"])
    result = {
        "question": req.question,
        "sql": plan["sql"],
        "engine": plan["engine"],
        "chart": plan["chart"],
        "answer": plan["answer"],
        "columns": list(df.columns),
        "rows": normalize_records(df),
        "row_count": int(len(df)),
        "dataset": meta,
    }
    h = history()
    h.insert(0, {"id": uuid.uuid4().hex[:8], "dataset_id": req.dataset_id, "question": req.question, "answer": result["answer"], "sql": result["sql"]})
    save_json(HISTORY_FILE, h[:100])
    return result


@app.get("/api/history")
def get_history(dataset_id: str | None = None):
    items = history()
    return [x for x in items if not dataset_id or x["dataset_id"] == dataset_id]


@app.delete("/api/datasets/{dataset_id}")
def delete_dataset(dataset_id: str):
    dataset_by_id(dataset_id)
    db = DATA_DIR / f"{dataset_id}.duckdb"
    csv = UPLOAD_DIR / f"{dataset_id}.csv"
    db.unlink(missing_ok=True)
    csv.unlink(missing_ok=True)
    save_json(META_FILE, [d for d in datasets() if d["id"] != dataset_id])
    return {"deleted": dataset_id}


@app.post("/api/db/connect")
def db_connect(req: DBConnectRequest):
    # Optional trusted-server connection test. The app does not persist the credential.
    try:
        from sqlalchemy import create_engine, inspect
        engine = create_engine(req.connection_string, pool_pre_ping=True)
        inspector = inspect(engine)
        tables = inspector.get_table_names()[:50]
        return {"name": req.name, "status": "connected", "tables": tables}
    except Exception as exc:
        raise HTTPException(400, f"Database connection failed: {exc}") from exc


@app.exception_handler(Exception)
async def unhandled(_, exc):
    return JSONResponse(status_code=500, content={"detail": str(exc)})

