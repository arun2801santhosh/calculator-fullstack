
import json
import os
from io import BytesIO
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image
)


app = FastAPI(title="Project Cost Control System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "project_data.json")


# --------------------------------------------------
# ORIGINAL PROJECT BUDGET
# These values are protected from website editing.
# --------------------------------------------------

DEFAULT_DATA = {
    "project": {
        "name": "",
        "code": "",
        "contractor": "",
        "start_month": "2026-12",
        "duration": 20,
        "report_month": "2026-12"
    },

    "budget": [
        {
            "id": 1,
            "description": "Project Staff",
            "tender_budget": 17619670,
            "initial_finalized": 17619670,
            "committed_cost": 17619670
        },
        {
            "id": 2,
            "description": "Labours",
            "tender_budget": 16000000,
            "initial_finalized": 15000000,
            "committed_cost": 14000000
        },
        {
            "id": 3,
            "description": "Equipments",
            "tender_budget": 18000000,
            "initial_finalized": 17000000,
            "committed_cost": 16000000
        },
        {
            "id": 4,
            "description": "Materials",
            "tender_budget": 19000000,
            "initial_finalized": 16000000,
            "committed_cost": 15000000
        }
    ],

    "expenses": [],
    "forecasts": []
}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)


def load_data():
    if not os.path.exists(DATA_FILE):
        save_data(DEFAULT_DATA)
        return json.loads(json.dumps(DEFAULT_DATA))

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        raise RuntimeError(
            "project_data.json is damaged. Restore a valid backup before continuing."
        )

    # Keep the original budget from the protected defaults.
    data["budget"] = json.loads(json.dumps(DEFAULT_DATA["budget"]))

    data.setdefault("project", {})
    data.setdefault("expenses", [])
    data.setdefault("forecasts", [])

    for key, value in DEFAULT_DATA["project"].items():
        data["project"].setdefault(key, value)

    save_data(data)
    return data


def get_months(project):
    start = datetime.strptime(project["start_month"], "%Y-%m")
    duration = int(project["duration"])

    months = []

    for i in range(duration):
        month_number = start.month - 1 + i
        year = start.year + month_number // 12
        month = month_number % 12 + 1
        months.append(f"{year}-{month:02d}")

    return months


def validate_month(month, project):
    try:
        datetime.strptime(month, "%Y-%m")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid month format.")

    if month not in get_months(project):
        raise HTTPException(
            status_code=400,
            detail="Month is outside the project duration."
        )


def find_budget_item(category_id, data):
    for item in data["budget"]:
        if item["id"] == category_id:
            return item

    raise HTTPException(status_code=404, detail="Budget category not found.")


def calculate_report(month, data):
    project = data["project"]
    validate_month(month, project)

    rows = []

    for index, item in enumerate(data["budget"], start=1):

        previous = sum(
            float(expense["amount"])
            for expense in data["expenses"]
            if expense["category_id"] == item["id"]
            and expense["month"] < month
        )

        current = sum(
            float(expense["amount"])
            for expense in data["expenses"]
            if expense["category_id"] == item["id"]
            and expense["month"] == month
        )

        remaining = sum(
            float(forecast["amount"])
            for forecast in data["forecasts"]
            if forecast["category_id"] == item["id"]
            and forecast["month"] > month
        )

        total = previous + current + remaining

        rows.append({
            "sr": index,
            "description": item["description"],
            "tender_budget": item["tender_budget"],
            "initial_finalized": item["initial_finalized"],
            "committed_cost": item["committed_cost"],
            "previous": previous,
            "current": current,
            "remaining": remaining,
            "total": total,
            "difference": total - item["committed_cost"]
        })

    totals = {
        key: sum(row[key] for row in rows)
        for key in [
            "tender_budget",
            "initial_finalized",
            "committed_cost",
            "previous",
            "current",
            "remaining",
            "total",
            "difference"
        ]
    }

    return {
        "month": month,
        "rows": rows,
        "totals": totals
    }


# --------------------------------------------------
# REQUEST MODELS
# --------------------------------------------------

class ProjectUpdate(BaseModel):
    name: str
    code: str = ""
    contractor: str = ""
    start_month: str
    duration: int = Field(gt=0, le=120)
    report_month: str = ""


class MonthlyEntry(BaseModel):
    month: str
    category_id: int
    amount: float = Field(ge=0)


class AmountUpdate(BaseModel):
    amount: float = Field(ge=0)


# --------------------------------------------------
# MAIN ROUTES
# --------------------------------------------------

@app.get("/")
def home():
    return {
        "message": "Project Cost Control System API is running."
    }


@app.get("/project")
def get_project():
    data = load_data()

    return {
        "project": data["project"],
        "budget": data["budget"],
        "expenses": data["expenses"],
        "forecasts": data["forecasts"]
    }


@app.put("/project")
def update_project(request: ProjectUpdate):
    data = load_data()

    try:
        datetime.strptime(request.start_month, "%Y-%m")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid start month.")

    months = get_months({
        "start_month": request.start_month,
        "duration": request.duration
    })

    report_month = request.report_month or data["project"]["report_month"]

    if report_month not in months:
        report_month = months[0]

    # Do not allow project dates to exclude existing records.
    existing_months = [
        item["month"]
        for item in data["expenses"] + data["forecasts"]
    ]

    if any(month not in months for month in existing_months):
        raise HTTPException(
            status_code=400,
            detail="Project duration cannot exclude saved monthly records."
        )

    data["project"] = {
        "name": request.name,
        "code": request.code,
        "contractor": request.contractor,
        "start_month": request.start_month,
        "duration": request.duration,
        "report_month": report_month
    }

    save_data(data)

    return {
        "message": "Project information saved.",
        "project": data["project"],
        "budget": data["budget"],
        "expenses": data["expenses"],
        "forecasts": data["forecasts"]
    }


# --------------------------------------------------
# MONTHLY ACTUAL COSTS
# --------------------------------------------------

@app.post("/expenses")
def add_expense(request: MonthlyEntry):
    data = load_data()

    validate_month(request.month, data["project"])
    find_budget_item(request.category_id, data)

    existing = next(
        (
            item for item in data["expenses"]
            if item["month"] == request.month
            and item["category_id"] == request.category_id
        ),
        None
    )

    if existing:
        existing["amount"] = request.amount
    else:
        new_id = max(
            [item["id"] for item in data["expenses"]],
            default=0
        ) + 1

        data["expenses"].append({
            "id": new_id,
            "month": request.month,
            "category_id": request.category_id,
            "amount": request.amount
        })

    save_data(data)

    return {"message": "Monthly actual cost saved."}


@app.get("/expenses")
def get_expenses():
    return load_data()["expenses"]


@app.put("/expenses/{expense_id}")
def update_expense(expense_id: int, request: AmountUpdate):
    data = load_data()

    for item in data["expenses"]:
        if item["id"] == expense_id:
            item["amount"] = request.amount
            save_data(data)
            return {"message": "Monthly actual cost updated."}

    raise HTTPException(status_code=404, detail="Expense not found.")


@app.delete("/expenses/{expense_id}")
def delete_expense(expense_id: int):
    data = load_data()

    original_length = len(data["expenses"])

    data["expenses"] = [
        item for item in data["expenses"]
        if item["id"] != expense_id
    ]

    if len(data["expenses"]) == original_length:
        raise HTTPException(status_code=404, detail="Expense not found.")

    save_data(data)

    return {"message": "Monthly actual cost deleted."}


# --------------------------------------------------
# MONTHLY FORECASTS
# --------------------------------------------------

@app.post("/forecasts")
def add_forecast(request: MonthlyEntry):
    data = load_data()

    validate_month(request.month, data["project"])
    find_budget_item(request.category_id, data)

    existing = next(
        (
            item for item in data["forecasts"]
            if item["month"] == request.month
            and item["category_id"] == request.category_id
        ),
        None
    )

    if existing:
        existing["amount"] = request.amount
    else:
        new_id = max(
            [item["id"] for item in data["forecasts"]],
            default=0
        ) + 1

        data["forecasts"].append({
            "id": new_id,
            "month": request.month,
            "category_id": request.category_id,
            "amount": request.amount
        })

    save_data(data)

    return {"message": "Monthly forecast saved."}


@app.get("/forecasts")
def get_forecasts():
    return load_data()["forecasts"]


@app.put("/forecasts/{forecast_id}")
def update_forecast(forecast_id: int, request: AmountUpdate):
    data = load_data()

    for item in data["forecasts"]:
        if item["id"] == forecast_id:
            item["amount"] = request.amount
            save_data(data)
            return {"message": "Monthly forecast updated."}

    raise HTTPException(status_code=404, detail="Forecast not found.")


@app.delete("/forecasts/{forecast_id}")
def delete_forecast(forecast_id: int):
    data = load_data()

    original_length = len(data["forecasts"])

    data["forecasts"] = [
        item for item in data["forecasts"]
        if item["id"] != forecast_id
    ]

    if len(data["forecasts"]) == original_length:
        raise HTTPException(status_code=404, detail="Forecast not found.")

    save_data(data)

    return {"message": "Monthly forecast deleted."}


# --------------------------------------------------
# COST REPORT
# --------------------------------------------------

@app.get("/report")
def get_report(month: str):
    data = load_data()
    return calculate_report(month, data)


# --------------------------------------------------
# PDF REPORT WITH GRAPH
# --------------------------------------------------

@app.get("/export-pdf")
def export_pdf(month: str):
    data = load_data()
    report = calculate_report(month, data)

    pdf_buffer = BytesIO()

    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=landscape(A3),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm
    )

    styles = getSampleStyleSheet()
    story = []

    project = data["project"]

    story.append(Paragraph(
        "CONSTRUCTION PROJECT COST CONTROL REPORT",
        styles["Title"]
    ))

    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph(
        f"Project: {project['name']} | "
        f"Code: {project['code']} | "
        f"Main Contractor: {project['contractor']}",
        styles["Normal"]
    ))

    story.append(Paragraph(
        f"Report Month: {month} | "
        f"Project Duration: {project['start_month']} "
        f"to {get_months(project)[-1]}",
        styles["Normal"]
    ))

    story.append(Spacer(1, 7 * mm))

    headings = [
        "Sr.No",
        "Description",
        "Tender Budget",
        "Initial Finalized",
        "Committed Cost",
        "Previous Cost",
        "Current Cost",
        "Remaining Forecast",
        "Total Forecast",
        "Overrun / Saving"
    ]

    table_data = [headings]

    for row in report["rows"]:
        table_data.append([
            row["sr"],
            row["description"],
            f"{row['tender_budget']:,.2f}",
            f"{row['initial_finalized']:,.2f}",
            f"{row['committed_cost']:,.2f}",
            f"{row['previous']:,.2f}",
            f"{row['current']:,.2f}",
            f"{row['remaining']:,.2f}",
            f"{row['total']:,.2f}",
            f"{row['difference']:,.2f}"
        ])

    totals = report["totals"]

    table_data.append([
        "",
        "TOTAL",
        f"{totals['tender_budget']:,.2f}",
        f"{totals['initial_finalized']:,.2f}",
        f"{totals['committed_cost']:,.2f}",
        f"{totals['previous']:,.2f}",
        f"{totals['current']:,.2f}",
        f"{totals['remaining']:,.2f}",
        f"{totals['total']:,.2f}",
        f"{totals['difference']:,.2f}"
    ])

    table = Table(
        table_data,
        repeatRows=1,
        colWidths=[
            12 * mm, 30 * mm, 32 * mm, 32 * mm, 32 * mm,
            30 * mm, 30 * mm, 35 * mm, 32 * mm, 32 * mm
        ]
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#102a43")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#dbeafe")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (1, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7)
    ]))

    story.append(table)
    story.append(Spacer(1, 10 * mm))

    # Graph
    labels = [row["description"] for row in report["rows"]]
    committed = [row["committed_cost"] for row in report["rows"]]
    forecast = [row["total"] for row in report["rows"]]

    figure, axis = plt.subplots(figsize=(10, 4))

    positions = list(range(len(labels)))
    width = 0.35

    axis.bar(
        [position - width / 2 for position in positions],
        committed,
        width,
        label="Committed Cost"
    )

    axis.bar(
        [position + width / 2 for position in positions],
        forecast,
        width,
        label="Total Forecast"
    )

    axis.set_xticks(positions)
    axis.set_xticklabels(labels)
    axis.set_ylabel("AED")
    axis.set_title(f"Committed Cost vs Forecast - {month}")
    axis.legend()
    axis.grid(axis="y", alpha=0.2)

    figure.tight_layout()

    graph_buffer = BytesIO()
    figure.savefig(graph_buffer, format="png", dpi=150)
    plt.close(figure)
    graph_buffer.seek(0)

    story.append(Image(graph_buffer, width=230 * mm, height=90 * mm))

    document.build(story)

    pdf_buffer.seek(0)

    filename = f"Project_Cost_Report_{month}.pdf"

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )
