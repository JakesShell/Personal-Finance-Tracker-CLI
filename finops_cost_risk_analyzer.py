import argparse
import csv
import json
from datetime import datetime
from html import escape
from pathlib import Path

JSON_DATA_FILE = Path("data/cloud_costs.json")
CSV_DATA_FILE = Path("data/cloud_costs.csv")

REPORT_TXT_FILE = Path("reports/finops_cost_risk_report.txt")
REPORT_JSON_FILE = Path("reports/finops_cost_risk_report.json")
REPORT_CSV_FILE = Path("reports/finops_cost_risk_report.csv")

ALERT_FILE = Path("alerts/finops_anomaly_alerts.txt")
LOG_FILE = Path("logs/cost_events.log")
DASHBOARD_FILE = Path("dashboard/finops-dashboard.html")

DAYS_IN_MONTH = 30
SPIKE_THRESHOLD_PERCENT = 30
LOW_UTILIZATION_THRESHOLD = 10


def load_costs_json():
    with JSON_DATA_FILE.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def load_costs_csv():
    records = []

    with CSV_DATA_FILE.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            records.append(
                {
                    "service": row["service"],
                    "resource": row["resource"],
                    "business_area": row["business_area"],
                    "monthly_budget": float(row["monthly_budget"]),
                    "current_spend": float(row["current_spend"]),
                    "previous_month_spend": float(row["previous_month_spend"]),
                    "owner": row["owner"],
                    "criticality": row["criticality"],
                    "utilization_percent": float(row["utilization_percent"]),
                }
            )

    return records


def log_event(resource, event_type, message, environment):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(
            f"{datetime.now().isoformat(timespec='seconds')} | "
            f"{environment.upper()} | {event_type} | {resource} | {message}\n"
        )


def calculate_spend_delta(current_spend, previous_month_spend):
    if previous_month_spend == 0:
        return 100.0

    return ((current_spend - previous_month_spend) / previous_month_spend) * 100


def forecast_month_end_spend(current_spend, day_of_month):
    safe_day = max(1, min(day_of_month, DAYS_IN_MONTH))
    return (current_spend / safe_day) * DAYS_IN_MONTH


def determine_blast_radius(record):
    criticality = record["criticality"].lower()
    service = record["service"].lower()

    if criticality == "critical":
        return "CRITICAL"

    if service in ["database", "compute", "gpu"] or criticality == "high":
        return "HIGH"

    if criticality == "medium":
        return "MEDIUM"

    return "LOW"


def build_findings(record, projected_spend, spike_percent):
    findings = []

    if record["current_spend"] > record["monthly_budget"]:
        findings.append("Current spend exceeds monthly budget")

    if projected_spend > record["monthly_budget"]:
        findings.append("Projected month-end spend exceeds monthly budget")

    if spike_percent >= SPIKE_THRESHOLD_PERCENT:
        findings.append("Cost spike detected compared to previous month")

    if not record.get("owner"):
        findings.append("Missing resource owner")

    if record["utilization_percent"] <= LOW_UTILIZATION_THRESHOLD:
        findings.append("Low utilization suggests possible waste")

    return findings


def calculate_risk_score(findings, blast_radius):
    score = 0

    if "Current spend exceeds monthly budget" in findings:
        score += 5

    if "Projected month-end spend exceeds monthly budget" in findings:
        score += 5

    if "Cost spike detected compared to previous month" in findings:
        score += 4

    if "Missing resource owner" in findings:
        score += 3

    if "Low utilization suggests possible waste" in findings:
        score += 3

    if blast_radius == "CRITICAL":
        score += 4
    elif blast_radius == "HIGH":
        score += 2
    elif blast_radius == "MEDIUM":
        score += 1

    return score


def classify_risk(score):
    if score >= 14:
        return "HIGH"

    if score >= 7:
        return "MEDIUM"

    return "LOW"


def risk_sort_value(risk_level):
    order = {
        "HIGH": 1,
        "MEDIUM": 2,
        "LOW": 3
    }

    return order.get(risk_level, 99)


def generate_action_plan(record, findings, risk_level):
    actions = []

    if "Missing resource owner" in findings:
        actions.append("Assign a responsible owner for the resource.")

    if "Current spend exceeds monthly budget" in findings:
        actions.append("Open a cost review and compare spend against approved budget.")

    if "Projected month-end spend exceeds monthly budget" in findings:
        actions.append("Create or tighten budget alert thresholds before month end.")

    if "Cost spike detected compared to previous month" in findings:
        actions.append("Investigate workload, query, traffic, or retention changes causing the spike.")

    if "Low utilization suggests possible waste" in findings:
        actions.append("Right-size, pause, archive, or downgrade the resource if business impact allows.")

    if record["service"].lower() == "database":
        actions.append("Review database query load, backup retention, storage growth, and scaling configuration.")

    if record["service"].lower() == "storage":
        actions.append("Review lifecycle policies, storage tiering, duplicate files, and stale objects.")

    if record["service"].lower() in ["gpu", "compute"]:
        actions.append("Review instance size, scheduling windows, autoscaling rules, and idle runtime.")

    if risk_level == "HIGH":
        actions.append("Escalate to engineering, operations, and finance for same-day remediation.")

    if not actions:
        actions.append("Continue routine cost monitoring.")

    return actions


def analyze_record(record, environment, day_of_month):
    spike_percent = calculate_spend_delta(
        record["current_spend"],
        record["previous_month_spend"]
    )

    projected_spend = forecast_month_end_spend(record["current_spend"], day_of_month)
    projected_overrun = max(0, projected_spend - record["monthly_budget"])
    blast_radius = determine_blast_radius(record)
    findings = build_findings(record, projected_spend, spike_percent)
    risk_score = calculate_risk_score(findings, blast_radius)
    risk_level = classify_risk(risk_score)
    action_plan = generate_action_plan(record, findings, risk_level)

    if risk_level == "HIGH":
        log_event(record["resource"], "ALERT", "High-risk FinOps anomaly detected", environment)
    elif risk_level == "MEDIUM":
        log_event(record["resource"], "REVIEW", "Cost risk requires follow-up review", environment)
    else:
        log_event(record["resource"], "AUDIT", "Resource passed FinOps cost checks", environment)

    return {
        "service": record["service"],
        "resource": record["resource"],
        "business_area": record["business_area"],
        "owner": record["owner"] if record["owner"] else "UNASSIGNED",
        "criticality": record["criticality"],
        "blast_radius": blast_radius,
        "monthly_budget": record["monthly_budget"],
        "current_spend": record["current_spend"],
        "previous_month_spend": record["previous_month_spend"],
        "projected_month_end_spend": round(projected_spend, 2),
        "projected_overrun": round(projected_overrun, 2),
        "spike_percent": round(spike_percent, 2),
        "utilization_percent": record["utilization_percent"],
        "findings": findings,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "action_plan": action_plan,
    }


def analyze_costs(records, environment, day_of_month):
    if LOG_FILE.exists():
        LOG_FILE.unlink()

    results = [analyze_record(record, environment, day_of_month) for record in records]

    return sorted(
        results,
        key=lambda item: (
            risk_sort_value(item["risk_level"]),
            -item["projected_overrun"],
            -item["risk_score"]
        )
    )


def build_executive_summary(results, environment, source, day_of_month):
    total_budget = sum(item["monthly_budget"] for item in results)
    current_spend = sum(item["current_spend"] for item in results)
    projected_spend = sum(item["projected_month_end_spend"] for item in results)
    projected_overrun = max(0, projected_spend - total_budget)
    high_risk = sum(1 for item in results if item["risk_level"] == "HIGH")
    medium_risk = sum(1 for item in results if item["risk_level"] == "MEDIUM")
    unowned_spend = sum(item["current_spend"] for item in results if item["owner"] == "UNASSIGNED")
    waste_candidates = sum(1 for item in results if "Low utilization suggests possible waste" in item["findings"])
    overrun_percent = (projected_overrun / total_budget) * 100 if total_budget else 0

    return {
        "environment": environment.upper(),
        "source": source.upper(),
        "forecast_day": day_of_month,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_monthly_budget": round(total_budget, 2),
        "total_current_spend": round(current_spend, 2),
        "projected_month_end_spend": round(projected_spend, 2),
        "projected_month_end_overrun": round(projected_overrun, 2),
        "projected_overrun_percent": round(overrun_percent, 2),
        "high_risk_resources": high_risk,
        "medium_risk_resources": medium_risk,
        "unowned_current_spend": round(unowned_spend, 2),
        "waste_candidates": waste_candidates,
        "immediate_action_required": "YES" if high_risk > 0 or projected_overrun > 0 else "NO",
    }


def generate_text_report(results, summary):
    REPORT_TXT_FILE.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "Cloud FinOps Anomaly Detection And Cost Risk Report",
        "=" * 68,
        "Executive Risk Summary",
        "-" * 68,
        f"Environment: {summary['environment']}",
        f"Source: {summary['source']}",
        f"Forecast Day: {summary['forecast_day']}",
        f"Generated At: {summary['generated_at']}",
        f"Total Monthly Budget: ${summary['total_monthly_budget']:.2f}",
        f"Total Current Spend: ${summary['total_current_spend']:.2f}",
        f"Projected Month-End Spend: ${summary['projected_month_end_spend']:.2f}",
        f"Projected Month-End Overrun: ${summary['projected_month_end_overrun']:.2f}",
        f"Projected Overrun Percent: {summary['projected_overrun_percent']:.2f}%",
        f"High-Risk Resources: {summary['high_risk_resources']}",
        f"Medium-Risk Resources: {summary['medium_risk_resources']}",
        f"Unowned Current Spend: ${summary['unowned_current_spend']:.2f}",
        f"Waste Candidates: {summary['waste_candidates']}",
        f"Immediate Action Required: {summary['immediate_action_required']}",
        "",
    ]

    for item in results:
        lines.append(f"Service: {item['service']}")
        lines.append(f"Resource: {item['resource']}")
        lines.append(f"Affected Area: {item['business_area']}")
        lines.append(f"Business Impact: {item['blast_radius']}")
        lines.append(f"Owner: {item['owner']}")
        lines.append(f"Monthly Budget: ${item['monthly_budget']:.2f}")
        lines.append(f"Current Spend: ${item['current_spend']:.2f}")
        lines.append(f"Projected Month-End Spend: ${item['projected_month_end_spend']:.2f}")
        lines.append(f"Projected Overrun: ${item['projected_overrun']:.2f}")
        lines.append(f"Previous Month Spend: ${item['previous_month_spend']:.2f}")
        lines.append(f"Spend Change: {item['spike_percent']}%")
        lines.append(f"Utilization: {item['utilization_percent']}%")
        lines.append(f"Risk Score: {item['risk_score']}")
        lines.append(f"Risk Level: {item['risk_level']}")

        if item["findings"]:
            lines.append("Findings:")
            for finding in item["findings"]:
                lines.append(f"- {finding}")
        else:
            lines.append("Findings: No major issues detected")

        lines.append("Recommended Action Plan:")
        for index, action in enumerate(item["action_plan"], start=1):
            lines.append(f"{index}. {action}")

        lines.append("-" * 68)

    REPORT_TXT_FILE.write_text("\n".join(lines), encoding="utf-8")


def export_json_report(results, summary):
    REPORT_JSON_FILE.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "executive_summary": summary,
        "results": results,
    }

    REPORT_JSON_FILE.write_text(json.dumps(output, indent=2), encoding="utf-8")


def export_csv_report(results):
    REPORT_CSV_FILE.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "service",
        "resource",
        "business_area",
        "owner",
        "blast_radius",
        "monthly_budget",
        "current_spend",
        "projected_month_end_spend",
        "projected_overrun",
        "spike_percent",
        "utilization_percent",
        "risk_score",
        "risk_level",
    ]

    with REPORT_CSV_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for item in results:
            writer.writerow({field: item[field] for field in fieldnames})


def write_budget_alerts(results, summary):
    ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "FinOps Budget Anomaly Alerts",
        "=" * 36,
        f"Immediate Action Required: {summary['immediate_action_required']}",
        f"Projected Month-End Overrun: ${summary['projected_month_end_overrun']:.2f}",
        f"Projected Overrun Percent: {summary['projected_overrun_percent']:.2f}%",
        "",
    ]

    high_risk_items = [item for item in results if item["risk_level"] == "HIGH"]

    if not high_risk_items:
        lines.append("No high-risk FinOps anomalies detected.")
    else:
        for item in high_risk_items:
            lines.append(
                f"{item['resource']} | {item['service']} | {item['blast_radius']} | "
                f"Projected Overrun: ${item['projected_overrun']:.2f}"
            )
            lines.append(f"Action: {item['action_plan'][0]}")
            lines.append("-" * 36)

    ALERT_FILE.write_text("\n".join(lines), encoding="utf-8")


def budget_bar(current_value, max_value):
    if max_value <= 0:
        percent = 0
    else:
        percent = min(100, max(0, (current_value / max_value) * 100))

    return round(percent, 2)


def build_metric_card(label, value, note=""):
    return f"""
    <article class="metric-card">
      <span>{escape(label)}</span>
      <strong>{escape(str(value))}</strong>
      <small>{escape(note)}</small>
    </article>
    """


def generate_priority_queue(results):
    high_priority = [item for item in results if item["risk_level"] in ["HIGH", "MEDIUM"]]

    if not high_priority:
        return """
        <section class="priority-panel">
          <div class="priority-header">
            <p class="kicker">Priority Queue</p>
            <h2>No urgent FinOps items detected</h2>
          </div>
        </section>
        """

    rows = []

    for index, item in enumerate(high_priority[:5], start=1):
        first_finding = item["findings"][0] if item["findings"] else "Routine monitoring"
        first_action = item["action_plan"][0] if item["action_plan"] else "Continue monitoring"

        rows.append(
            f"""
            <tr>
              <td>{index}</td>
              <td>{escape(item['resource'])}</td>
              <td>{escape(item['risk_level'])}</td>
              <td>{escape(first_finding)}</td>
              <td>{escape(first_action)}</td>
            </tr>
            """
        )

    return f"""
    <section class="priority-panel" id="risk-queue">
      <div class="priority-header">
        <div>
          <p class="kicker">Priority Queue</p>
          <h2>What the team should fix first</h2>
        </div>
        <span>{len(high_priority)} active review items</span>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Priority</th>
              <th>Resource</th>
              <th>Risk</th>
              <th>Primary Issue</th>
              <th>First Action</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rows)}
          </tbody>
        </table>
      </div>
    </section>
    """


def generate_dashboard(results, summary):
    DASHBOARD_FILE.parent.mkdir(parents=True, exist_ok=True)

    metric_cards = "".join(
        [
            build_metric_card("Projected Month-End Spend", f"${summary['projected_month_end_spend']:.2f}", "Forecast exposure"),
            build_metric_card("Projected Overrun", f"${summary['projected_month_end_overrun']:.2f}", "Budget risk"),
            build_metric_card("High-Risk Resources", summary["high_risk_resources"], "Immediate review"),
            build_metric_card("Unowned Spend", f"${summary['unowned_current_spend']:.2f}", "Ownership gap"),
            build_metric_card("Waste Candidates", summary["waste_candidates"], "Low utilization"),
            build_metric_card("Current Spend", f"${summary['total_current_spend']:.2f}", "Spend to date"),
        ]
    )

    warning_strip = f"""
    <section class="warning-strip">
      <strong>Executive Warning:</strong>
      <span>Projected spend exceeds approved monthly budget by {summary['projected_overrun_percent']:.2f}%. Immediate FinOps review is recommended.</span>
    </section>
    """

    priority_queue = generate_priority_queue(results)

    resource_cards = []

    for item in results:
        findings = "".join(f"<li>{escape(finding)}</li>" for finding in item["findings"]) or "<li>No major issues detected</li>"
        actions = "".join(f"<li>{escape(action)}</li>" for action in item["action_plan"])
        risk_class = item["risk_level"].lower()
        current_bar = budget_bar(item["current_spend"], item["monthly_budget"])
        projected_bar = budget_bar(item["projected_month_end_spend"], item["monthly_budget"])

        resource_cards.append(
            f"""
            <section class="resource-card risk-{risk_class}" id="resources">
              <div class="resource-topline">
                <div>
                  <p class="kicker">{escape(item['service'])} / {escape(item['business_area'])}</p>
                  <h2>{escape(item['resource'])}</h2>
                </div>
                <div class="risk-badge badge-{risk_class}">{escape(item['risk_level'])}</div>
              </div>

              <div class="resource-metrics">
                <div><span>Business Impact</span><strong>{escape(item['blast_radius'])}</strong></div>
                <div><span>Owner</span><strong>{escape(item['owner'])}</strong></div>
                <div><span>Current Spend</span><strong>${item['current_spend']:.2f}</strong></div>
                <div><span>Projected Spend</span><strong>${item['projected_month_end_spend']:.2f}</strong></div>
                <div><span>Projected Overrun</span><strong>${item['projected_overrun']:.2f}</strong></div>
                <div><span>Utilization</span><strong>{item['utilization_percent']}%</strong></div>
              </div>

              <div class="bar-panel">
                <div class="bar-row">
                  <div class="bar-label">
                    <span>Current Spend Vs Budget</span>
                    <strong>${item['current_spend']:.2f} / ${item['monthly_budget']:.2f}</strong>
                  </div>
                  <div class="bar-track"><div class="bar-fill current" style="width:{current_bar}%"></div></div>
                </div>

                <div class="bar-row">
                  <div class="bar-label">
                    <span>Projected Spend Vs Budget</span>
                    <strong>${item['projected_month_end_spend']:.2f} / ${item['monthly_budget']:.2f}</strong>
                  </div>
                  <div class="bar-track"><div class="bar-fill projected" style="width:{projected_bar}%"></div></div>
                </div>
              </div>

              <div class="resource-detail">
                <div>
                  <h3>Findings</h3>
                  <ul>{findings}</ul>
                </div>
                <div>
                  <h3>Action Plan</h3>
                  <ol>{actions}</ol>
                </div>
              </div>
            </section>
            """
        )

    html = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Cloud FinOps Cost Risk Dashboard</title>
  <style>
    :root {
      --ink: #182118;
      --muted: #6f6a5d;
      --paper: #f7f1e4;
      --cream: #fffaf0;
      --green: #13281d;
      --green-soft: #20372b;
      --gold: #b08a3c;
      --gold-soft: #d8c28a;
      --oxblood: #6d1f1b;
      --line: rgba(39, 49, 37, 0.18);
      --shadow: 0 24px 70px rgba(20, 25, 18, 0.18);
    }

    * {
      box-sizing: border-box;
      scroll-behavior: smooth;
    }

    body {
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(176, 138, 60, 0.18), transparent 28%),
        linear-gradient(135deg, #efe4cf 0%, #f7f1e4 42%, #e7dcc8 100%);
      font-family: "Segoe UI", Arial, sans-serif;
    }

    .page {
      width: min(1180px, calc(100% - 42px));
      margin: 0 auto;
      padding: 44px 0 60px;
    }

    .nav {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 22px;
      color: var(--green);
      font-size: 0.78rem;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      font-weight: 700;
    }

    .nav-links {
      display: flex;
      gap: 18px;
      align-items: center;
    }

    .nav-links a {
      color: var(--green);
      text-decoration: none;
      border-bottom: 1px solid transparent;
      padding-bottom: 4px;
    }

    .nav-links a:hover {
      border-bottom-color: var(--gold);
    }

    .seal {
      width: 42px;
      height: 42px;
      border-radius: 50%;
      border: 1px solid var(--gold);
      display: grid;
      place-items: center;
      color: var(--gold);
      font-family: Georgia, serif;
      letter-spacing: 0;
      font-size: 1.1rem;
      background: rgba(255, 250, 240, 0.65);
    }

    .hero {
      position: relative;
      overflow: hidden;
      padding: 36px;
      border-radius: 30px;
      background:
        linear-gradient(135deg, rgba(255, 250, 240, 0.94), rgba(242, 231, 209, 0.92)),
        repeating-linear-gradient(90deg, rgba(19, 40, 29, 0.03) 0, rgba(19, 40, 29, 0.03) 1px, transparent 1px, transparent 14px);
      border: 1px solid rgba(176, 138, 60, 0.34);
      box-shadow: var(--shadow);
    }

    .hero:before {
      content: "";
      position: absolute;
      inset: 18px;
      border: 1px solid rgba(176, 138, 60, 0.24);
      border-radius: 22px;
      pointer-events: none;
    }

    .hero-grid {
      position: relative;
      display: grid;
      grid-template-columns: 1.15fr 0.85fr;
      gap: 34px;
      align-items: end;
      z-index: 1;
    }

    .kicker {
      margin: 0 0 10px;
      color: var(--gold);
      text-transform: uppercase;
      letter-spacing: 0.16em;
      font-size: 0.74rem;
      font-weight: 800;
    }

    h1 {
      margin: 0;
      max-width: 780px;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--green);
      font-size: clamp(2.5rem, 5vw, 5.4rem);
      line-height: 0.95;
      letter-spacing: -0.06em;
    }

    .hero-copy {
      margin: 22px 0 0;
      max-width: 720px;
      color: var(--muted);
      font-size: 1.02rem;
      line-height: 1.75;
    }

    .executive-panel {
      border-radius: 24px;
      padding: 24px;
      background: var(--green);
      color: var(--cream);
      border: 1px solid rgba(216, 194, 138, 0.42);
      box-shadow: inset 0 0 0 1px rgba(255, 250, 240, 0.06);
    }

    .executive-panel span {
      display: block;
      color: var(--gold-soft);
      font-size: 0.78rem;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      margin-bottom: 10px;
    }

    .executive-panel strong {
      display: block;
      font-family: Georgia, serif;
      font-size: 2.1rem;
      line-height: 1;
    }

    .executive-panel p {
      margin: 14px 0 0;
      color: #e7dcc8;
      line-height: 1.55;
    }

    .report-meta {
      margin-top: 18px;
      font-size: 0.76rem;
      color: var(--gold-soft);
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .metric-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
      margin-top: 24px;
    }

    .metric-card {
      padding: 22px;
      border-radius: 22px;
      background: rgba(255, 250, 240, 0.72);
      border: 1px solid var(--line);
      box-shadow: 0 12px 32px rgba(20, 25, 18, 0.08);
    }

    .metric-card span {
      display: block;
      color: var(--muted);
      font-size: 0.78rem;
      margin-bottom: 8px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 700;
    }

    .metric-card strong {
      display: block;
      font-family: Georgia, serif;
      color: var(--green);
      font-size: 2rem;
      line-height: 1.05;
    }

    .metric-card small {
      display: block;
      color: var(--gold);
      margin-top: 8px;
      font-weight: 700;
    }

    .warning-strip {
      margin: 24px 0;
      padding: 18px 22px;
      border-radius: 20px;
      background: rgba(109, 31, 27, 0.95);
      color: var(--cream);
      border: 1px solid rgba(216, 194, 138, 0.5);
      box-shadow: 0 16px 36px rgba(109, 31, 27, 0.18);
      display: flex;
      gap: 10px;
      align-items: center;
      line-height: 1.5;
    }

    .warning-strip strong {
      color: var(--gold-soft);
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-size: 0.8rem;
      white-space: nowrap;
    }

    .priority-panel {
      margin: 24px 0 34px;
      padding: 26px;
      border-radius: 26px;
      background: rgba(255, 250, 240, 0.78);
      border: 1px solid rgba(176, 138, 60, 0.36);
      box-shadow: 0 18px 42px rgba(20, 25, 18, 0.12);
    }

    .priority-header {
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: end;
      margin-bottom: 18px;
    }

    .priority-header h2 {
      margin: 0;
      color: var(--green);
      font-family: Georgia, serif;
      font-size: 1.75rem;
    }

    .priority-header span {
      color: var(--gold);
      font-weight: 800;
      font-size: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .table-wrap {
      overflow-x: auto;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 780px;
    }

    th {
      text-align: left;
      color: var(--green);
      font-size: 0.72rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      padding: 12px;
      border-bottom: 1px solid var(--line);
    }

    td {
      padding: 14px 12px;
      color: #39382f;
      border-bottom: 1px solid rgba(39, 49, 37, 0.1);
      vertical-align: top;
    }

    .section-title {
      margin: 42px 0 16px;
      display: flex;
      align-items: center;
      gap: 14px;
      color: var(--green);
      font-family: Georgia, serif;
      font-size: 1.65rem;
    }

    .section-title:after {
      content: "";
      height: 1px;
      background: var(--line);
      flex: 1;
    }

    .resource-card {
      margin-top: 18px;
      padding: 26px;
      border-radius: 26px;
      background: rgba(255, 250, 240, 0.82);
      border: 1px solid var(--line);
      box-shadow: 0 18px 42px rgba(20, 25, 18, 0.11);
    }

    .risk-high {
      border-left: 7px solid var(--oxblood);
    }

    .risk-medium {
      border-left: 7px solid var(--gold);
    }

    .risk-low {
      border-left: 7px solid var(--green-soft);
    }

    .resource-topline {
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: start;
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
    }

    .resource-topline h2 {
      margin: 0;
      font-family: Georgia, serif;
      color: var(--green);
      font-size: 1.65rem;
    }

    .risk-badge {
      padding: 9px 14px;
      border-radius: 999px;
      color: var(--cream);
      border: 1px solid rgba(176, 138, 60, 0.45);
      font-size: 0.78rem;
      font-weight: 800;
      letter-spacing: 0.08em;
    }

    .badge-high {
      background: var(--oxblood);
    }

    .badge-medium {
      background: var(--gold);
      color: var(--ink);
    }

    .badge-low {
      background: var(--green);
    }

    .resource-metrics {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }

    .resource-metrics div {
      padding: 15px;
      border-radius: 16px;
      background: rgba(239, 228, 207, 0.54);
      border: 1px solid rgba(39, 49, 37, 0.12);
    }

    .resource-metrics span {
      display: block;
      color: var(--muted);
      font-size: 0.74rem;
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .resource-metrics strong {
      color: var(--green);
      font-family: Georgia, serif;
      font-size: 1.2rem;
    }

    .bar-panel {
      margin-top: 18px;
      padding: 18px;
      border-radius: 18px;
      background: rgba(239, 228, 207, 0.36);
      border: 1px solid rgba(39, 49, 37, 0.1);
    }

    .bar-row + .bar-row {
      margin-top: 16px;
    }

    .bar-label {
      display: flex;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 8px;
      color: var(--muted);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-weight: 700;
    }

    .bar-label strong {
      color: var(--green);
      font-family: Georgia, serif;
      letter-spacing: 0;
    }

    .bar-track {
      height: 12px;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(19, 40, 29, 0.12);
      border: 1px solid rgba(19, 40, 29, 0.1);
    }

    .bar-fill {
      height: 100%;
      border-radius: 999px;
    }

    .bar-fill.current {
      background: linear-gradient(90deg, var(--green-soft), var(--gold));
    }

    .bar-fill.projected {
      background: linear-gradient(90deg, var(--gold), var(--oxblood));
    }

    .resource-detail {
      display: grid;
      grid-template-columns: 0.9fr 1.3fr;
      gap: 22px;
      margin-top: 20px;
    }

    h3 {
      margin: 0 0 10px;
      color: var(--green);
      font-family: Georgia, serif;
    }

    li {
      margin-bottom: 8px;
      color: #39382f;
      line-height: 1.45;
    }

    .footer-note {
      margin: 38px auto 0;
      text-align: center;
      color: var(--muted);
      font-size: 0.92rem;
    }

    @media (max-width: 900px) {
      .hero-grid,
      .metric-grid,
      .resource-metrics,
      .resource-detail {
        grid-template-columns: 1fr;
      }

      .resource-topline,
      .priority-header,
      .warning-strip {
        flex-direction: column;
        align-items: flex-start;
      }

      .nav {
        gap: 14px;
        flex-direction: column;
      }

      .nav-links {
        flex-wrap: wrap;
        justify-content: center;
      }
    }
  </style>
</head>
<body>
  <main class="page">
    <nav class="nav">
      <div>FinOps Risk Office</div>
      <div class="seal">F</div>
      <div class="nav-links">
        <a href="#summary">Executive Summary</a>
        <a href="#risk-queue">Risk Queue</a>
        <a href="#resources">Resources</a>
      </div>
    </nav>

    <section class="hero" id="summary">
      <div class="hero-grid">
        <div>
          <p class="kicker">Cloud Financial Incident Prevention</p>
          <h1>Cost Risk, Forecasting, And Budget Control.</h1>
          <p class="hero-copy">
            A polished FinOps dashboard for identifying projected overspend, high-risk resources,
            unowned spend, low-utilization waste, business impact, and immediate remediation priorities.
          </p>
        </div>

        <aside class="executive-panel">
          <span>Immediate Action Required</span>
          <strong>__ACTION_REQUIRED__</strong>
          <p>Projected month-end overrun: <strong style="font-size:1.35rem; display:inline;">$__OVERRUN__</strong></p>
          <div class="report-meta">Generated __GENERATED_AT__ · __ENVIRONMENT__ · Source __SOURCE__ · Forecast Day __FORECAST_DAY__</div>
        </aside>
      </div>

      <div class="metric-grid">
        __METRIC_CARDS__
      </div>
    </section>

    __WARNING_STRIP__

    __PRIORITY_QUEUE__

    <h2 class="section-title">Resource Risk Review</h2>

    __RESOURCE_CARDS__

    <p class="footer-note">Generated by the Cloud FinOps Anomaly Detection And Cost Risk System.</p>
  </main>
</body>
</html>
"""

    html = html.replace("__ACTION_REQUIRED__", escape(summary["immediate_action_required"]))
    html = html.replace("__OVERRUN__", f"{summary['projected_month_end_overrun']:.2f}")
    html = html.replace("__GENERATED_AT__", escape(summary["generated_at"]))
    html = html.replace("__ENVIRONMENT__", escape(summary["environment"]))
    html = html.replace("__SOURCE__", escape(summary["source"]))
    html = html.replace("__FORECAST_DAY__", escape(str(summary["forecast_day"])))
    html = html.replace("__METRIC_CARDS__", metric_cards)
    html = html.replace("__WARNING_STRIP__", warning_strip)
    html = html.replace("__PRIORITY_QUEUE__", priority_queue)
    html = html.replace("__RESOURCE_CARDS__", "".join(resource_cards))

    DASHBOARD_FILE.write_text(html, encoding="utf-8")


def print_api_response(results, summary):
    response = {
        "service": "cloud-finops-risk-api",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "executive_summary": summary,
        "results": results,
    }

    print(json.dumps(response, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Cloud FinOps Anomaly Detection And Cost Risk System")
    parser.add_argument("--env", default="dev", help="Environment name, for example dev, test, or prod")
    parser.add_argument("--source", choices=["json", "csv"], default="json", help="Cost input source")
    parser.add_argument("--day", type=int, default=12, help="Current day of month used for forecasting")
    parser.add_argument("--export-json", action="store_true", help="Export machine-readable JSON report")
    parser.add_argument("--export-csv", action="store_true", help="Export CSV report for operations teams")
    parser.add_argument("--dashboard", action="store_true", help="Generate old-money executive HTML dashboard")
    parser.add_argument("--api-output", action="store_true", help="Print API-style JSON response to console")

    args = parser.parse_args()

    if args.source == "json":
        records = load_costs_json()
    else:
        records = load_costs_csv()

    results = analyze_costs(records, args.env, args.day)
    summary = build_executive_summary(results, args.env, args.source, args.day)

    generate_text_report(results, summary)
    write_budget_alerts(results, summary)

    if args.export_json:
        export_json_report(results, summary)

    if args.export_csv:
        export_csv_report(results)

    if args.dashboard:
        generate_dashboard(results, summary)

    if args.api_output:
        print_api_response(results, summary)
    else:
        print("Cloud FinOps Anomaly Detection And Cost Risk System")
        print("=" * 68)
        print("FinOps cost risk analysis completed successfully.")
        print(f"Environment: {args.env.upper()}")
        print(f"Source: {args.source.upper()}")
        print(f"Forecast Day: {args.day}")
        print(f"Text report created: {REPORT_TXT_FILE}")
        print(f"Alert file created: {ALERT_FILE}")

        if args.export_json:
            print(f"JSON report created: {REPORT_JSON_FILE}")

        if args.export_csv:
            print(f"CSV report created: {REPORT_CSV_FILE}")

        if args.dashboard:
            print(f"Dashboard created: {DASHBOARD_FILE}")

        print(f"Event log updated: {LOG_FILE}")
        print("")
        print(REPORT_TXT_FILE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
