"""Static dashboard rendering for Agent Mesh."""

from __future__ import annotations

import json
from typing import Iterable


def build_dashboard_payload(config, work_items: Iterable[object], claims: Iterable[object], reviews: Iterable[object], *, public: bool = False) -> dict:
    work_items = list(work_items)
    claims = list(claims)
    reviews = list(reviews)
    work_index = {item.id: item for item in work_items}

    status_counts = count_by_attr(work_items, "status")
    kind_counts = count_by_attr(work_items, "kind")
    risk_counts = count_by_attr(work_items, "risk")
    total = len(work_items)
    done = status_counts.get("done", 0)
    progress_pct = int(done / total * 100) if total else 0

    tasks = [
        {
            "id": item.id,
            "title": item.title,
            "status": item.status,
            "kind": getattr(item, "kind", "unknown"),
            "risk": getattr(item, "risk", "unknown"),
            "module": getattr(item, "module", None),
            "updatedAt": getattr(item, "updated_at", None),
            "createdAt": getattr(item, "created_at", None),
            "description": None if public else getattr(item, "description", ""),
            "acceptanceCriteria": [] if public else list(getattr(item, "acceptance_criteria", [])),
            "dependencies": [] if public else list(getattr(item, "dependencies", [])),
            "execution": None if public else getattr(item, "execution", None),
        }
        for item in sorted(work_items, key=task_sort_key)
    ]

    active_work = []
    for claim in claims:
        work_item = work_index.get(claim.work_id)
        active_work.append(
            {
                "workId": claim.work_id,
                "title": work_item.title if work_item else claim.work_id,
                "status": getattr(claim, "status", "in_progress"),
                "kind": getattr(work_item, "kind", "unknown") if work_item else "unknown",
                "risk": getattr(work_item, "risk", "unknown") if work_item else "unknown",
                "module": getattr(work_item, "module", None) if work_item else None,
                "role": getattr(claim, "role", None),
                "agent": None if public else getattr(claim, "agent_runtime", None),
                "branch": None if public else getattr(claim, "branch", None),
                "workspaceId": None if public else getattr(claim, "workspace_id", None),
                "worktree": None if public else getattr(claim, "worktree", None),
                "claimedAt": getattr(claim, "claimed_at", None),
                "lastSeen": getattr(claim, "last_seen", None),
            }
        )

    review_cards = []
    for review in reviews:
        work_item = work_index.get(review.work_id)
        review_cards.append(
            {
                "id": review.id,
                "publicLabel": review.work_id,
                "workId": review.work_id,
                "title": work_item.title if work_item else review.work_id,
                "status": review.status,
                "branch": None if public else getattr(review.pr, "branch", None),
                "base": None if public else getattr(review.pr, "base", None),
                "url": None if public else getattr(review.pr, "url", None),
                "requestedRole": getattr(review, "requested_role", None),
                "createdAt": getattr(review, "created_at", None),
            }
        )

    return {
        "project": {
            "name": config.project_name,
            "key": config.project_key,
        },
        "meta": {
            "mode": "public" if public else "internal",
            "public": public,
        },
        "summary": {
            "totalTasks": total,
            "doneTasks": done,
            "progressPct": progress_pct,
            "readyTasks": status_counts.get("ready", 0),
            "inProgressTasks": status_counts.get("in_progress", 0),
            "blockedTasks": status_counts.get("blocked", 0),
            "pendingReviews": sum(1 for review in reviews if review.status == "pending_review"),
            "mergedReviews": sum(1 for review in reviews if review.status == "merged"),
            "activeClaims": len(claims),
            "statusCounts": dict(sorted(status_counts.items())),
            "kindCounts": dict(sorted(kind_counts.items())),
            "riskCounts": dict(sorted(risk_counts.items())),
        },
        "tasks": tasks,
        "activeWork": active_work,
        "reviews": review_cards,
    }


def render_dashboard_html(payload: dict) -> str:
    import html as _html

    e = _html.escape
    public = bool(payload["meta"]["public"])
    summary = payload["summary"]
    project = payload["project"]
    data_json = _json_for_script(payload)
    export_note = (
        '<div class="mode-banner">Public snapshot: sensitive coordination fields are redacted for internet sharing.</div>'
        if public
        else '<div class="mode-banner">Internal snapshot: includes local coordination details for operators.</div>'
    )
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{project_name} dashboard</title>
  <style>
    :root {{
      --bg: #f4efe4;
      --panel: rgba(255, 252, 247, 0.92);
      --panel-strong: #fffdf8;
      --ink: #102a43;
      --muted: #52606d;
      --line: rgba(16, 42, 67, 0.12);
      --accent: #c2410c;
      --accent-soft: #ffedd5;
      --secondary: #0f766e;
      --secondary-soft: #ccfbf1;
      --warning: #b45309;
      --warning-soft: #fef3c7;
      --danger: #b91c1c;
      --danger-soft: #fee2e2;
      --shadow: 0 24px 48px rgba(16, 42, 67, 0.08);
      --radius: 22px;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; }}
    body {{
      min-height: 100vh;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(194, 65, 12, 0.18), transparent 28%),
        radial-gradient(circle at top right, rgba(15, 118, 110, 0.16), transparent 22%),
        linear-gradient(180deg, #fffaf1 0%, var(--bg) 100%);
    }}
    a {{ color: inherit; }}
    .shell {{
      max-width: 1240px;
      margin: 0 auto;
      padding: 28px 20px 40px;
    }}
    .hero {{
      position: relative;
      overflow: hidden;
      background:
        linear-gradient(140deg, rgba(16, 42, 67, 0.98), rgba(8, 60, 70, 0.94)),
        linear-gradient(90deg, rgba(255,255,255,0.04), rgba(255,255,255,0));
      border-radius: 28px;
      padding: 32px;
      color: #f8fafc;
      box-shadow: var(--shadow);
    }}
    .hero::after {{
      content: "";
      position: absolute;
      inset: auto -50px -60px auto;
      width: 220px;
      height: 220px;
      border-radius: 999px;
      background: radial-gradient(circle, rgba(255,255,255,0.18), transparent 65%);
      pointer-events: none;
    }}
    .eyebrow {{
      letter-spacing: 0.18em;
      text-transform: uppercase;
      font-size: 0.72rem;
      opacity: 0.72;
      margin-bottom: 10px;
    }}
    .hero-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.5fr) minmax(260px, 0.9fr);
      gap: 24px;
      align-items: end;
    }}
    .hero h1 {{
      margin: 0;
      font-size: clamp(2rem, 5vw, 3.9rem);
      line-height: 0.94;
      letter-spacing: -0.04em;
      max-width: 10ch;
    }}
    .hero p {{
      margin: 14px 0 0;
      max-width: 52ch;
      color: rgba(248, 250, 252, 0.82);
      font-size: 1rem;
    }}
    .hero-metrics {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    .metric {{
      background: rgba(255,255,255,0.08);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 18px;
      padding: 14px 16px;
      backdrop-filter: blur(8px);
    }}
    .metric strong {{
      display: block;
      font-size: 1.65rem;
      line-height: 1;
      margin-bottom: 4px;
    }}
    .metric span {{
      color: rgba(248, 250, 252, 0.72);
      font-size: 0.84rem;
    }}
    .mode-banner {{
      margin-top: 18px;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 10px 14px;
      border-radius: 999px;
      background: rgba(255,255,255,0.1);
      color: rgba(248, 250, 252, 0.88);
      font-size: 0.84rem;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin-top: 20px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }}
    .stat-card {{
      padding: 20px;
    }}
    .stat-card .label {{
      color: var(--muted);
      font-size: 0.78rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .stat-card .value {{
      margin-top: 12px;
      font-size: clamp(1.7rem, 3vw, 2.7rem);
      line-height: 0.95;
      letter-spacing: -0.05em;
    }}
    .stat-card .sub {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 0.88rem;
    }}
    .strip {{
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 16px;
      margin-top: 18px;
    }}
    .panel-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 20px 22px 0;
    }}
    .panel-head h2 {{
      margin: 0;
      font-size: 1rem;
      letter-spacing: -0.03em;
    }}
    .panel-head .hint {{
      color: var(--muted);
      font-size: 0.84rem;
    }}
    .chip-row {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      padding: 16px 22px 0;
    }}
    .chip {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: var(--panel-strong);
      font-size: 0.82rem;
      color: var(--muted);
    }}
    .chip button {{
      border: 0;
      padding: 0;
      background: none;
      color: inherit;
      font: inherit;
      cursor: pointer;
    }}
    .list {{
      padding: 18px 22px 22px;
      display: grid;
      gap: 12px;
    }}
    .list-item {{
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255,255,255,0.74);
      padding: 16px;
    }}
    .list-item-top {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
    }}
    .list-item h3 {{
      margin: 0;
      font-size: 1rem;
      letter-spacing: -0.02em;
    }}
    .list-item .meta {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 0.84rem;
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .controls {{
      margin-top: 18px;
      padding: 20px 22px;
      display: grid;
      grid-template-columns: minmax(0, 1.3fr) repeat(4, minmax(0, 0.6fr));
      gap: 12px;
      align-items: center;
    }}
    .control {{
      display: grid;
      gap: 6px;
    }}
    .control label {{
      font-size: 0.75rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .control input,
    .control select {{
      width: 100%;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.82);
      color: var(--ink);
      padding: 12px 14px;
      font: inherit;
      outline: none;
    }}
    .control input:focus,
    .control select:focus {{
      border-color: rgba(194, 65, 12, 0.4);
      box-shadow: 0 0 0 4px rgba(194, 65, 12, 0.12);
    }}
    .table-wrap {{
      overflow: auto;
      padding: 0 6px 14px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 920px;
    }}
    thead th {{
      position: sticky;
      top: 0;
      background: rgba(255, 252, 247, 0.98);
      text-align: left;
      font-size: 0.76rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--muted);
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
    }}
    tbody td {{
      vertical-align: top;
      padding: 14px 16px;
      border-bottom: 1px solid rgba(16, 42, 67, 0.08);
    }}
    tbody tr {{
      transition: background 160ms ease, transform 160ms ease;
    }}
    tbody tr:hover {{
      background: rgba(255,255,255,0.68);
    }}
    .task-title {{
      font-weight: 700;
      letter-spacing: -0.02em;
    }}
    .task-notes {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 0.84rem;
      line-height: 1.45;
    }}
    .mono {{
      font-family: "SFMono-Regular", Consolas, monospace;
      font-size: 0.82rem;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 0.76rem;
      font-weight: 700;
      letter-spacing: 0.01em;
      white-space: nowrap;
    }}
    .empty {{
      padding: 22px;
      color: var(--muted);
      text-align: center;
    }}
    .footer-note {{
      margin-top: 14px;
      color: var(--muted);
      font-size: 0.82rem;
      padding: 0 4px;
    }}
    .page-footer {{
      margin-top: 18px;
      text-align: center;
      color: var(--muted);
      font-size: 0.82rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }}
    @media (max-width: 1080px) {{
      .stats,
      .strip,
      .controls,
      .hero-grid {{
        grid-template-columns: 1fr;
      }}
    }}
    @media (max-width: 720px) {{
      .shell {{ padding: 18px 14px 28px; }}
      .hero {{ padding: 22px; }}
      .panel-head,
      .chip-row,
      .controls,
      .list {{
        padding-left: 16px;
        padding-right: 16px;
      }}
      .mode-banner {{ border-radius: 18px; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div class="eyebrow">Agent Mesh dashboard</div>
      <div class="hero-grid">
        <div>
          <h1>{project_name}</h1>
          <p>Live view of visible work, progress, and review flow for <strong>{project_key}</strong>.</p>
        </div>
        <div class="hero-metrics">
          <div class="metric"><strong>{progress_pct}%</strong><span>Overall progress</span></div>
          <div class="metric"><strong>{active_claims}</strong><span>Active workstreams</span></div>
          <div class="metric"><strong>{ready_tasks}</strong><span>Ready tasks</span></div>
          <div class="metric"><strong>{pending_reviews}</strong><span>Pending reviews</span></div>
        </div>
      </div>
      {export_note}
    </section>

    <section class="stats">
      <div class="card stat-card">
        <div class="label">Completed</div>
        <div class="value">{done_tasks}</div>
        <div class="sub">{done_tasks} of {total_tasks} tasks are done.</div>
      </div>
      <div class="card stat-card">
        <div class="label">In Progress</div>
        <div class="value">{in_progress_tasks}</div>
        <div class="sub">{active_claims} active claims mapped to current work.</div>
      </div>
      <div class="card stat-card">
        <div class="label">Merged Reviews</div>
        <div class="value">{merged_reviews}</div>
        <div class="sub">Review packets already merged or closed.</div>
      </div>
      <div class="card stat-card">
        <div class="label">Blocked</div>
        <div class="value">{blocked_tasks}</div>
        <div class="sub">Flagged blockers in the visible work graph.</div>
      </div>
    </section>

    <section class="strip">
      <div class="card">
        <div class="panel-head">
          <h2>Task Mix</h2>
          <div class="hint">Quick filters for the task table</div>
        </div>
        <div id="status-chips" class="chip-row"></div>
        <div id="kind-chips" class="chip-row" style="padding-top:10px;"></div>
      </div>
      <div class="card">
        <div class="panel-head">
          <h2>Risk Spread</h2>
          <div class="hint">Visible task risk levels</div>
        </div>
        <div id="risk-chips" class="chip-row"></div>
        <div class="footer-note">Public exports keep project progress visible while hiding machine paths, branches, and workspace routing.</div>
      </div>
    </section>

    <section class="strip">
      <div class="card">
        <div class="panel-head">
          <h2>Active Work</h2>
          <div class="hint">{active_work_hint}</div>
        </div>
        <div id="active-work" class="list"></div>
      </div>
      <div class="card">
        <div class="panel-head">
          <h2>Reviews</h2>
          <div class="hint">{review_hint}</div>
        </div>
        <div id="reviews" class="list"></div>
      </div>
    </section>

    <section class="card" style="margin-top:18px;">
      <div class="panel-head">
        <h2>Task Explorer</h2>
        <div class="hint">Search, filter, and sort the current work graph</div>
      </div>
      <div class="controls">
        <div class="control">
          <label for="task-search">Search</label>
          <input id="task-search" type="search" placeholder="Search title, module, id, or description">
        </div>
        <div class="control">
          <label for="status-filter">Status</label>
          <select id="status-filter"></select>
        </div>
        <div class="control">
          <label for="kind-filter">Kind</label>
          <select id="kind-filter"></select>
        </div>
        <div class="control">
          <label for="risk-filter">Risk</label>
          <select id="risk-filter"></select>
        </div>
        <div class="control">
          <label for="sort-filter">Sort</label>
          <select id="sort-filter"></select>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Task</th>
              <th>Status</th>
              <th>Kind</th>
              <th>Risk</th>
              <th>Module</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody id="task-rows"></tbody>
        </table>
      </div>
      <div id="task-empty" class="empty" hidden>No tasks match the current filters.</div>
    </section>
    <div class="page-footer">Powered by Mesh</div>
  </div>

  <script>
    const payload = {payload_json};
    const state = {{
      search: "",
      status: "all",
      kind: "all",
      risk: "all",
      sort: "priority"
    }};

    const statusOrder = {{ in_progress: 0, review: 1, ready: 2, blocked: 3, done: 4 }};
    const riskOrder = {{ high: 0, medium: 1, low: 2 }};
    const statusTheme = {{
      done: ["#166534", "#dcfce7"],
      ready: ["#1d4ed8", "#dbeafe"],
      in_progress: ["#b45309", "#fef3c7"],
      blocked: ["#991b1b", "#fee2e2"],
      pending_review: ["#5b21b6", "#ede9fe"],
      merged: ["#334155", "#e2e8f0"]
    }};
    const kindTheme = {{
      feature: ["#115e59", "#ccfbf1"],
      bug: ["#991b1b", "#fee2e2"],
      security: ["#5b21b6", "#ede9fe"],
      refactor: ["#334155", "#e2e8f0"]
    }};
    const riskTheme = {{
      high: ["#991b1b", "#fee2e2"],
      medium: ["#92400e", "#fef3c7"],
      low: ["#166534", "#dcfce7"]
    }};

    function escapeHtml(value) {{
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }}

    function badge(text, theme) {{
      const colors = theme || ["#334155", "#e2e8f0"];
      return `<span class="badge" style="color:${{colors[0]}};background:${{colors[1]}}">${{escapeHtml(text)}}</span>`;
    }}

    function formatWhen(value) {{
      if (!value) {{
        return "-";
      }}
      return value.replace("T", " ").replace("Z", " UTC");
    }}

    function normalize(value) {{
      return String(value || "").toLowerCase();
    }}

    function installSelect(id, values) {{
      const select = document.getElementById(id);
      const label = id.split("-")[0];
      const options = ['<option value="all">All ' + escapeHtml(label) + '</option>']
        .concat(values.map((value) => `<option value="${{escapeHtml(value)}}">${{escapeHtml(value)}}</option>`));
      select.innerHTML = options.join("");
    }}

    function renderCountChips(containerId, counts, category) {{
      const container = document.getElementById(containerId);
      const keys = Object.keys(counts);
      if (!keys.length) {{
        container.innerHTML = '<div class="chip">No data</div>';
        return;
      }}
      container.innerHTML = keys.map((key) => {{
        const value = counts[key];
        return `<div class="chip"><button type="button" data-category="${{category}}" data-value="${{escapeHtml(key)}}">${{escapeHtml(key)}}: <strong>${{value}}</strong></button></div>`;
      }}).join("");
    }}

    function activeWorkMarkup(item) {{
      const meta = [];
      if (item.module) meta.push(`Module: ${{escapeHtml(item.module)}}`);
      if (item.role) meta.push(`Role: ${{escapeHtml(item.role)}}`);
      if (!payload.meta.public && item.agent) meta.push(`Agent: ${{escapeHtml(item.agent)}}`);
      if (!payload.meta.public && item.branch) meta.push(`Branch: ${{escapeHtml(item.branch)}}`);
      return `
        <article class="list-item">
          <div class="list-item-top">
            <div>
              <h3>${{escapeHtml(item.title)}}</h3>
              <div class="meta">
                <span class="mono">${{escapeHtml(item.workId)}}</span>
                <span>${{escapeHtml(item.kind)}}</span>
                <span>${{escapeHtml(item.risk)}} risk</span>
              </div>
            </div>
            ${{badge(item.status.replaceAll("_", " "), statusTheme[item.status] || statusTheme.in_progress)}}
          </div>
          <div class="meta">${{meta.map((entry) => `<span>${{entry}}</span>`).join("")}}</div>
        </article>
      `;
    }}

    function reviewMarkup(item) {{
      const label = payload.meta.public ? item.publicLabel : item.id;
      const meta = [];
      meta.push(`Work: ${{escapeHtml(item.workId)}}`);
      if (!payload.meta.public && item.branch) {{
        meta.push(`Branch: ${{escapeHtml(item.branch)}}`);
      }}
      if (item.requestedRole) {{
        meta.push(`Role: ${{escapeHtml(item.requestedRole)}}`);
      }}
      return `
        <article class="list-item">
          <div class="list-item-top">
            <div>
              <h3>${{escapeHtml(item.title)}}</h3>
              <div class="meta">
                <span class="mono">${{escapeHtml(label)}}</span>
                <span>${{escapeHtml(formatWhen(item.createdAt))}}</span>
              </div>
            </div>
            ${{badge(item.status.replaceAll("_", " "), statusTheme[item.status] || statusTheme.pending_review)}}
          </div>
          <div class="meta">${{meta.map((entry) => `<span>${{entry}}</span>`).join("")}}</div>
        </article>
      `;
    }}

    function renderLists() {{
      const active = document.getElementById("active-work");
      active.innerHTML = payload.activeWork.length
        ? payload.activeWork.map(activeWorkMarkup).join("")
        : '<div class="empty">No active work right now.</div>';

      const reviews = document.getElementById("reviews");
      reviews.innerHTML = payload.reviews.length
        ? payload.reviews.map(reviewMarkup).join("")
        : '<div class="empty">No review packets yet.</div>';
    }}

    function taskMatches(task) {{
      const query = normalize(state.search);
      const haystack = [
        task.id,
        task.title,
        task.module,
        task.status,
        task.kind,
        task.risk,
        task.description,
        (task.acceptanceCriteria || []).join(" ")
      ].map(normalize).join(" ");
      if (query && !haystack.includes(query)) return false;
      if (state.status !== "all" && task.status !== state.status) return false;
      if (state.kind !== "all" && task.kind !== state.kind) return false;
      if (state.risk !== "all" && task.risk !== state.risk) return false;
      return true;
    }}

    function sortTasks(tasks) {{
      const items = tasks.slice();
      items.sort((left, right) => {{
        if (state.sort === "title") {{
          return left.title.localeCompare(right.title) || left.id.localeCompare(right.id);
        }}
        if (state.sort === "updated") {{
          return String(right.updatedAt || "").localeCompare(String(left.updatedAt || "")) || left.id.localeCompare(right.id);
        }}
        if (state.sort === "risk") {{
          return (riskOrder[left.risk] ?? 9) - (riskOrder[right.risk] ?? 9)
            || (statusOrder[left.status] ?? 9) - (statusOrder[right.status] ?? 9)
            || left.id.localeCompare(right.id);
        }}
        if (state.sort === "status") {{
          return (statusOrder[left.status] ?? 9) - (statusOrder[right.status] ?? 9)
            || left.title.localeCompare(right.title);
        }}
        return (statusOrder[left.status] ?? 9) - (statusOrder[right.status] ?? 9)
          || (riskOrder[left.risk] ?? 9) - (riskOrder[right.risk] ?? 9)
          || left.id.localeCompare(right.id);
      }});
      return items;
    }}

    function taskRowMarkup(task) {{
      const notes = [];
      if (task.description) notes.push(escapeHtml(task.description));
      if (task.acceptanceCriteria && task.acceptanceCriteria.length) {{
        notes.push(`Acceptance: ${{task.acceptanceCriteria.length}} item(s)`);
      }}
      if (task.dependencies && task.dependencies.length) {{
        notes.push(`Dependencies: ${{task.dependencies.join(", ")}}`);
      }}
      return `
        <tr>
          <td class="mono">${{escapeHtml(task.id)}}</td>
          <td>
            <div class="task-title">${{escapeHtml(task.title)}}</div>
            <div class="task-notes">${{notes.length ? notes.join(" ") : "No additional task notes in this view."}}</div>
          </td>
          <td>${{badge(task.status.replaceAll("_", " "), statusTheme[task.status])}}</td>
          <td>${{badge(task.kind, kindTheme[task.kind])}}</td>
          <td>${{badge(task.risk, riskTheme[task.risk])}}</td>
          <td>${{task.module ? escapeHtml(task.module) : "-"}}</td>
          <td class="mono">${{escapeHtml(formatWhen(task.updatedAt || task.createdAt))}}</td>
        </tr>
      `;
    }}

    function renderTaskTable() {{
      const filtered = sortTasks(payload.tasks.filter(taskMatches));
      const body = document.getElementById("task-rows");
      const empty = document.getElementById("task-empty");
      body.innerHTML = filtered.map(taskRowMarkup).join("");
      empty.hidden = filtered.length !== 0;
    }}

    function wireControls() {{
      installSelect("status-filter", Object.keys(payload.summary.statusCounts));
      installSelect("kind-filter", Object.keys(payload.summary.kindCounts));
      installSelect("risk-filter", Object.keys(payload.summary.riskCounts));

      document.getElementById("sort-filter").innerHTML = [
        '<option value="priority">Priority</option>',
        '<option value="status">Status</option>',
        '<option value="risk">Risk</option>',
        '<option value="updated">Recently updated</option>',
        '<option value="title">Title</option>'
      ].join("");

      document.getElementById("task-search").addEventListener("input", (event) => {{
        state.search = event.target.value;
        renderTaskTable();
      }});
      document.getElementById("status-filter").addEventListener("change", (event) => {{
        state.status = event.target.value;
        renderTaskTable();
      }});
      document.getElementById("kind-filter").addEventListener("change", (event) => {{
        state.kind = event.target.value;
        renderTaskTable();
      }});
      document.getElementById("risk-filter").addEventListener("change", (event) => {{
        state.risk = event.target.value;
        renderTaskTable();
      }});
      document.getElementById("sort-filter").addEventListener("change", (event) => {{
        state.sort = event.target.value;
        renderTaskTable();
      }});

      document.querySelectorAll("[data-category]").forEach((button) => {{
        button.addEventListener("click", () => {{
          const category = button.dataset.category;
          const value = button.dataset.value;
          if (category === "status") {{
            state.status = value;
            document.getElementById("status-filter").value = value;
          }} else if (category === "kind") {{
            state.kind = value;
            document.getElementById("kind-filter").value = value;
          }} else if (category === "risk") {{
            state.risk = value;
            document.getElementById("risk-filter").value = value;
          }}
          renderTaskTable();
        }});
      }});
    }}

    renderCountChips("status-chips", payload.summary.statusCounts, "status");
    renderCountChips("kind-chips", payload.summary.kindCounts, "kind");
    renderCountChips("risk-chips", payload.summary.riskCounts, "risk");
    renderLists();
    wireControls();
    renderTaskTable();
  </script>
</body>
</html>
""".format(
        project_name=e(project["name"]),
        project_key=e(project["key"]),
        progress_pct=summary["progressPct"],
        active_claims=summary["activeClaims"],
        ready_tasks=summary["readyTasks"],
        pending_reviews=summary["pendingReviews"],
        done_tasks=summary["doneTasks"],
        total_tasks=summary["totalTasks"],
        in_progress_tasks=summary["inProgressTasks"],
        merged_reviews=summary["mergedReviews"],
        blocked_tasks=summary["blockedTasks"],
        active_work_hint="Redacted workspace metadata" if public else "Shows current lane and branch context",
        review_hint="Stakeholder-safe summary" if public else "Includes internal review routing",
        export_note=export_note,
        payload_json=data_json,
    )


def count_by_attr(items: Iterable[object], attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = str(getattr(item, attr, "unknown") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts


def task_sort_key(item: object) -> tuple[int, int, str]:
    status_rank = {
        "in_progress": 0,
        "review": 1,
        "ready": 2,
        "blocked": 3,
        "done": 4,
    }
    risk_rank = {
        "high": 0,
        "medium": 1,
        "low": 2,
    }
    return (
        status_rank.get(getattr(item, "status", ""), 9),
        risk_rank.get(getattr(item, "risk", ""), 9),
        getattr(item, "id", ""),
    )


def _json_for_script(payload: dict) -> str:
    return (
        json.dumps(payload, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("</", "<\\/")
    )
