"""AI Visibility Dashboard - Flask Web Application"""
import os
import json
import time
from datetime import datetime
from flask import Flask, jsonify, render_template_string, request

from scanner import scan_domain, check_chatgpt, generate_prompts, AiVisibilityReport, AiCheckResult

app = Flask(__name__)
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

HISTORY_FILE = os.path.join(DATA_DIR, "history.json")


def load_history():
    """Load scan history for trend tracking."""
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_history(domain: str, result: dict):
    """Save a scan result to history for trend tracking."""
    history = load_history()
    if domain not in history:
        history[domain] = []
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "overall_score": result.get("scores", {}).get("overall", 0),
        "technical_score": result.get("scores", {}).get("technical_readiness", 0),
        "schema_score": result.get("scores", {}).get("schema_readiness", 0),
        "content_score": result.get("scores", {}).get("content_quality", 0),
        "issues": result.get("summary", {}).get("issue_count", 0),
        "warnings": result.get("summary", {}).get("warn_count", 0),
    }
    history[domain].append(entry)
    # Keep last 30 scans
    history[domain] = history[domain][-30:]
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


# ====== DASHBOARD HTML ======
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Visibility Dashboard</title>
    <style>
        :root {
            --bg: #0a0a0a;
            --card: #111111;
            --border: #1e1e1e;
            --text: #f5f5f0;
            --muted: #888888;
            --accent: #e85d2f;
            --accent-hover: #d04d1f;
            --green: #22c55e;
            --yellow: #eab308;
            --red: #ef4444;
            --blue: #3b82f6;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
        }
        .container { max-width: 1240px; margin: 0 auto; padding: 0 24px; }

        /* Header */
        header {
            border-bottom: 1px solid var(--border);
            padding: 20px 0;
            position: sticky;
            top: 0;
            background: rgba(10,10,10,0.95);
            backdrop-filter: blur(12px);
            z-index: 100;
        }
        header .container {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .logo { font-size: 22px; font-weight: 800; letter-spacing: -0.02em; }
        .logo span { color: var(--accent); }
        .logo small {
            font-size: 12px;
            font-weight: 400;
            color: var(--muted);
            display: block;
            margin-top: 2px;
        }
        .scan-form { display: flex; gap: 12px; align-items: center; }
        .scan-form input {
            background: var(--card);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 10px 16px;
            border-radius: 6px;
            font-size: 14px;
            width: 220px;
            outline: none;
            transition: border-color 0.2s;
        }
        .scan-form input:focus { border-color: var(--accent); }
        .scan-form input::placeholder { color: #555; }
        .scan-btn {
            background: var(--accent);
            color: white;
            border: none;
            padding: 10px 24px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }
        .scan-btn:hover { background: var(--accent-hover); }
        .scan-btn:disabled { opacity: 0.5; cursor: not-allowed; }

        /* Scan Progress */
        #progress-bar {
            display: none;
            height: 3px;
            background: linear-gradient(90deg, var(--accent), var(--blue));
            position: fixed;
            top: 0;
            left: 0;
            z-index: 200;
            transition: width 0.5s ease;
        }
        #status-bar {
            display: none;
            text-align: center;
            padding: 16px 0;
            color: var(--muted);
            font-size: 14px;
            border-bottom: 1px solid var(--border);
        }
        #status-bar .spinner {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid var(--border);
            border-top-color: var(--accent);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            vertical-align: middle;
            margin-right: 8px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* Score Hero */
        .hero { padding: 40px 0 24px; }
        .hero-grid {
            display: grid;
            grid-template-columns: auto 1fr;
            gap: 32px;
            align-items: center;
        }
        .score-ring {
            width: 140px;
            height: 140px;
            position: relative;
        }
        .score-ring svg { transform: rotate(-90deg); }
        .score-ring .bg { fill: none; stroke: var(--border); stroke-width: 6; }
        .score-ring .fg {
            fill: none;
            stroke-width: 6;
            stroke-linecap: round;
            transition: stroke-dashoffset 1s ease;
        }
        .score-number {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            text-align: center;
        }
        .score-number .num { font-size: 36px; font-weight: 800; line-height: 1; }
        .score-number .label { font-size: 11px; color: var(--muted); margin-top: 4px; }
        .grade-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 14px;
            font-weight: 700;
            margin-top: 4px;
        }
        .hero-info h1 { font-size: 28px; font-weight: 700; }
        .hero-info .meta { color: var(--muted); font-size: 14px; margin-top: 6px; }
        .hero-info .meta span { margin-right: 20px; }

        /* Score Cards */
        .score-cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 32px;
        }
        .score-card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 20px;
        }
        .score-card .label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
        .score-card .value { font-size: 28px; font-weight: 700; margin-top: 6px; }
        .score-card .bar {
            height: 4px;
            border-radius: 2px;
            background: var(--border);
            margin-top: 12px;
            overflow: hidden;
        }
        .score-card .bar-fill {
            height: 100%;
            border-radius: 2px;
            transition: width 1s ease;
        }

        /* Engine Bar */
        .engine-bar {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 12px;
            margin-bottom: 32px;
        }
        .engine-item {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            text-align: center;
        }
        .engine-item .name { font-size: 13px; font-weight: 600; }
        .engine-item .status {
            font-size: 24px;
            font-weight: 700;
            margin-top: 6px;
        }
        .engine-item .desc { font-size: 11px; color: var(--muted); margin-top: 4px; }

        /* Sections */
        .section {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 24px;
            margin-bottom: 16px;
        }
        .section h3 {
            font-size: 16px;
            font-weight: 700;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .section h3 .count {
            font-size: 12px;
            font-weight: 400;
            color: var(--muted);
        }

        /* Check Items */
        .check-item {
            display: flex;
            align-items: flex-start;
            gap: 12px;
            padding: 12px 0;
            border-bottom: 1px solid var(--border);
        }
        .check-item:last-child { border-bottom: none; }
        .check-icon {
            width: 24px;
            height: 24px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            flex-shrink: 0;
        }
        .check-icon.pass { background: rgba(34,197,94,0.15); color: var(--green); }
        .check-icon.warn { background: rgba(234,179,8,0.15); color: var(--yellow); }
        .check-icon.issue { background: rgba(239,68,68,0.15); color: var(--red); }
        .check-text { flex: 1; }
        .check-text .title { font-size: 14px; font-weight: 500; }
        .check-text .detail { font-size: 12px; color: var(--muted); margin-top: 4px; }
        .check-text .fix {
            font-size: 12px;
            color: var(--accent);
            margin-top: 4px;
            padding: 6px 10px;
            background: rgba(232,93,47,0.08);
            border-radius: 4px;
            border-left: 2px solid var(--accent);
        }
        .check-text .fix strong { font-weight: 600; }

        /* Recommendations */
        .rec-item {
            padding: 14px 0;
            border-bottom: 1px solid var(--border);
            display: flex;
            gap: 12px;
            align-items: flex-start;
        }
        .rec-item:last-child { border-bottom: none; }
        .rec-priority {
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            padding: 3px 8px;
            border-radius: 4px;
            flex-shrink: 0;
        }
        .rec-priority.high { background: rgba(239,68,68,0.15); color: var(--red); }
        .rec-priority.medium { background: rgba(234,179,8,0.15); color: var(--yellow); }

        /* Schema display */
        .schema-types {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 8px;
        }
        .schema-type {
            background: rgba(59,130,246,0.1);
            color: var(--blue);
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
        }

        /* Trend Chart Placeholder */
        .trend-chart {
            display: flex;
            align-items: flex-end;
            gap: 4px;
            height: 80px;
            padding: 20px 0 0;
        }
        .trend-bar {
            flex: 1;
            background: var(--accent);
            border-radius: 2px 2px 0 0;
            opacity: 0.7;
            min-height: 4px;
            transition: height 0.3s ease;
            position: relative;
        }
        .trend-bar:hover { opacity: 1; }

        /* Score legend */
        .legend { display: flex; gap: 20px; margin-bottom: 16px; }
        .legend-item { font-size: 12px; color: var(--muted); display: flex; align-items: center; gap: 6px; }
        .legend-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }

        /* Empty state */
        .empty-state {
            text-align: center;
            padding: 80px 20px;
            color: var(--muted);
        }
        .empty-state h2 { font-size: 22px; color: var(--text); margin-bottom: 8px; }
        .empty-state p { font-size: 14px; max-width: 400px; margin: 0 auto; line-height: 1.6; }

        /* Hidden */
        .hidden { display: none; }

        @media (max-width: 768px) {
            header .container { flex-direction: column; gap: 12px; }
            .scan-form { width: 100%; }
            .scan-form input { flex: 1; }
            .hero-grid { grid-template-columns: 1fr; text-align: center; }
            .score-ring { margin: 0 auto; }
            .engine-bar { grid-template-columns: repeat(2, 1fr); }
        }
    </style>
</head>
<body>

<div id="progress-bar"></div>

<header>
    <div class="container">
        <div class="logo">
            AI Visibility <span>Dashboard</span>
            <small>BeFound · LLMScout · Evertune · Peec · AEO Checker — combined</small>
        </div>
        <form class="scan-form" id="scanForm">
            <input type="text" id="domainInput" placeholder="yourbusiness.com" required>
            <input type="text" id="bizInput" placeholder="Business name (optional)">
            <input type="text" id="cityInput" placeholder="City (optional)">
            <button type="submit" class="scan-btn" id="scanBtn">Scan Now</button>
        </form>
    </div>
</header>

<div id="status-bar">
    <span class="spinner"></span>
    <span id="statusText">Scanning your website across 25+ AI visibility checks...</span>
</div>

<main class="container">
    <div id="results" class="hidden">
        <div class="hero" id="heroSection"></div>
        <div class="score-cards" id="scoreCards"></div>
        <div class="engine-bar" id="engineBar"></div>
        <div id="sections"></div>
    </div>
    <div id="emptyState" class="empty-state">
        <h2>Check your AI visibility</h2>
        <p>Enter your website URL above to run a comprehensive audit across technical readiness, schema markup, content quality, AI crawler access, and social metadata — combining checks from BeFound.ai, LLMScout, Evertune, Peec, and AEO Authority Checker.</p>
        <p style="margin-top:16px;font-size:12px;color:#555">25+ automated checks · AI visibility scoring · Trend tracking · Fix recommendations</p>
    </div>
</main>

<script>
const CIRCUMFERENCE = 2 * Math.PI * 52;

function setScore(score, grade) {
    const offset = CIRCUMFERENCE - (score / 100) * CIRCUMFERENCE;
    document.getElementById('scoreCircle').style.strokeDashoffset = offset;
    document.getElementById('scoreNum').textContent = score;
    document.getElementById('gradeBadge').textContent = grade;
    const color = score >= 80 ? '#22c55e' : score >= 60 ? '#eab308' : '#ef4444';
    document.getElementById('scoreCircle').style.stroke = color;
    document.getElementById('gradeBadge').style.background = color + '22';
    document.getElementById('gradeBadge').style.color = color;
}

function renderResults(data) {
    document.getElementById('emptyState').classList.add('hidden');
    document.getElementById('results').classList.remove('hidden');
    
    const s = data.scores || {};
    
    // Hero
    document.getElementById('heroSection').innerHTML = `
        <div class="hero-grid">
            <div class="score-ring">
                <svg width="140" height="140" viewBox="0 0 120 120">
                    <circle class="bg" cx="60" cy="60" r="52"/>
                    <circle class="fg" id="scoreCircle" cx="60" cy="60" r="52"
                        stroke-dasharray="${CIRCUMFERENCE}" stroke-dashoffset="${CIRCUMFERENCE}"/>
                </svg>
                <div class="score-number">
                    <div class="num" id="scoreNum">${s.overall || 0}</div>
                    <div class="label">Overall Score</div>
                    <div class="grade-badge" id="gradeBadge"></div>
                </div>
            </div>
            <div class="hero-info">
                <h1>${data.summary.business_name || data.summary.domain}</h1>
                <div class="meta">
                    <span>Domain: ${data.summary.domain}</span>
                    <span>Checks: ${data.summary.total_checks}</span>
                    <span>Issues: ${data.summary.issue_count}</span>
                    <span>Warnings: ${data.summary.warn_count}</span>
                    <span>Grade: ${s.grade || 'N/A'}</span>
                </div>
            </div>
        </div>
    `;
    
    setScore(s.overall || 0, s.grade || 'N/A');
    
    // Score cards
    const scoreDefs = [
        { label: 'Technical Readiness', value: s.technical_readiness || 0, color: '#3b82f6' },
        { label: 'Schema / Structured Data', value: s.schema_readiness || 0, color: '#a855f7' },
        { label: 'Content Quality', value: s.content_quality || 0, color: '#22c55e' },
        { label: 'Social Metadata', value: s.social_meta || 0, color: '#f97316' },
        { label: 'Performance', value: s.performance || 0, color: '#06b6d4' },
    ];
    
    document.getElementById('scoreCards').innerHTML = scoreDefs.map(sd => `
        <div class="score-card">
            <div class="label">${sd.label}</div>
            <div class="value">${sd.value}</div>
            <div class="bar">
                <div class="bar-fill" style="width:${sd.value}%;background:${sd.color}"></div>
            </div>
        </div>
    `).join('');
    
    // Engine bar (estimated from crawler data)
    const crawlers = data.crawlers || {};
    const engines = [
        { name: 'ChatGPT', key: 'GPTBot', est: estimateEngine(crawlers, 'GPTBot'), color: '#10a37f' },
        { name: 'Gemini', key: 'Google-Extended', est: estimateEngine(crawlers, 'Google-Extended'), color: '#4285f4' },
        { name: 'Claude', key: 'ClaudeBot', est: estimateEngine(crawlers, 'ClaudeBot'), color: '#d97706' },
        { name: 'Perplexity', key: 'PerplexityBot', est: estimateEngine(crawlers, 'PerplexityBot'), color: '#1f2937' },
    ];
    
    document.getElementById('engineBar').innerHTML = engines.map(e => `
        <div class="engine-item">
            <div class="name">${e.name}</div>
            <div class="status" style="color:${e.est.color}">${e.est.text}</div>
            <div class="desc">${e.est.desc}</div>
        </div>
    `).join('');
    
    // Detail sections
    let sectionsHtml = '';
    
    // Technical checks
    if (data.technical) {
        sectionsHtml += buildSection('Technical AI Readiness', data.passes, data.warnings, data.issues);
    }
    
    // Schema section
    if (data.schema) {
        const sch = data.schema;
        const types = sch.types_found || [];
        sectionsHtml += `
            <div class="section">
                <h3>Structured Data / Schema.org</h3>
                <div style="font-size:13px;color:var(--muted);margin-bottom:12px">
                    JSON-LD scripts: ${sch.jsonld_count || 0} | 
                    Relevant types: ${(sch.relevant_types || []).length}
                </div>
                <div class="schema-types">
                    ${types.map(t => `<span class="schema-type">${t}</span>`).join('') || '<span style="color:var(--muted);font-size:13px">No schema types detected</span>'}
                </div>
                <div style="margin-top:12px;display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px">
                    <span style="font-size:13px;color:${sch.has_organization ? 'var(--green)' : 'var(--red)'}">${sch.has_organization ? '✓' : '✗'} Organization</span>
                    <span style="font-size:13px;color:${sch.has_local_business ? 'var(--green)' : 'var(--red)'}">${sch.has_local_business ? '✓' : '✗'} Local Business</span>
                    <span style="font-size:13px;color:${sch.has_faq ? 'var(--green)' : 'var(--red)'}">${sch.has_faq ? '✓' : '✗'} FAQPage</span>
                    <span style="font-size:13px;color:${sch.has_breadcrumbs ? 'var(--green)' : 'var(--red)'}">${sch.has_breadcrumbs ? '✓' : '✗'} Breadcrumbs</span>
                    <span style="font-size:13px;color:${sch.has_product ? 'var(--green)' : 'var(--red)'}">${sch.has_product ? '✓' : '✗'} Product</span>
                </div>
            </div>
        `;
    }
    
    // Content section
    if (data.content) {
        const c = data.content;
        sectionsHtml += `
            <div class="section">
                <h3>Content Quality Signals</h3>
                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;font-size:13px">
                    <div>Words: <strong>${c.word_count || data.technical?.content?.word_count || '?'}</strong></div>
                    <div>Substantial paragraphs: <strong>${c.substantial_paragraphs || 0}</strong></div>
                    <div>Lists: <strong>${c.lists_count || 0}</strong></div>
                    <div>Images with alt: <strong>${c.images_with_alt || 0} / ${c.images_total || 0}</strong></div>
                    <div>Email: <strong>${c.contact_info?.has_email ? '✓' : '✗'}</strong></div>
                    <div>Phone: <strong>${c.contact_info?.has_phone ? '✓' : '✗'}</strong></div>
                    <div>Address: <strong>${c.contact_info?.has_address ? '✓' : '✗'}</strong></div>
                </div>
            </div>
        `;
    }
    
    // Social section
    if (data.social) {
        const soc = data.social;
        sectionsHtml += `
            <div class="section">
                <h3>Social & Metadata</h3>
                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px;font-size:13px">
                    <span style="color:${soc.has_og_title ? 'var(--green)' : 'var(--red)'}">${soc.has_og_title ? '✓' : '✗'} og:title</span>
                    <span style="color:${soc.has_og_description ? 'var(--green)' : 'var(--red)'}">${soc.has_og_description ? '✓' : '✗'} og:description</span>
                    <span style="color:${soc.has_og_image ? 'var(--green)' : 'var(--red)'}">${soc.has_og_image ? '✓' : '✗'} og:image</span>
                    <span style="color:${soc.has_twitter_card ? 'var(--green)' : 'var(--red)'}">${soc.has_twitter_card ? '✓' : '✗'} Twitter Cards</span>
                </div>
            </div>
        `;
    }
    
    // Performance section
    if (data.performance) {
        const p = data.performance;
        sectionsHtml += `
            <div class="section">
                <h3>Performance & Security</h3>
                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px;font-size:13px">
                    <div>SSL: <strong style="color:${p.ssl?.valid ? 'var(--green)' : 'var(--red)'}">${p.ssl?.valid ? 'Valid' : 'Issues'}</strong></div>
                    <div>HTTP: <strong>${p.http_version || '?'}</strong></div>
                    <div>HTML Size: <strong>${p.html_size_kb || '?'} KB</strong></div>
                </div>
                ${p.ssl?.issuer ? `<div style="font-size:12px;color:var(--muted);margin-top:8px">SSL Issuer: ${p.ssl.issuer} | Expires: ${p.ssl.expiry}</div>` : ''}
            </div>
        `;
    }
    
    // Recommendations section
    const recs = data.recommendations || [];
    if (recs.length > 0) {
        sectionsHtml += `
            <div class="section">
                <h3>Recommendations <span class="count">(${recs.length} items)</span></h3>
                ${recs.map(r => `
                    <div class="rec-item">
                        <span class="rec-priority ${r.priority}">${r.priority}</span>
                        <div>
                            <div style="font-size:14px;font-weight:500">${r.message}</div>
                            ${r.fix ? `<div style="font-size:12px;color:var(--muted);margin-top:4px">${r.fix}</div>` : ''}
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }
    
    document.getElementById('sections').innerHTML = sectionsHtml;
}

function estimateEngine(crawlers, key) {
    const bot = crawlers[key];
    if (!bot || bot.status_code === 0) {
        return { text: '?', color: '#666', desc: 'Could not test' };
    }
    if (bot.accessible === false || (bot.status_code && bot.status_code >= 400)) {
        return { text: 'Blocked', color: 'var(--red)', desc: 'Not accessible' };
    }
    return { text: 'Accessible', color: 'var(--green)', desc: 'Crawlable' };
}

function buildSection(title, passes, warnings, issues) {
    const items = [
        ...(passes || []).map(p => ({ ...p, type: 'pass' })),
        ...(warnings || []).map(w => ({ ...w, type: 'warn' })),
        ...(issues || []).map(i => ({ ...i, type: 'issue' })),
    ];
    
    if (items.length === 0) return '';
    
    return `
        <div class="section">
            <h3>${title} <span class="count">(${items.length} checks)</span></h3>
            ${items.map(item => `
                <div class="check-item">
                    <div class="check-icon ${item.type}">
                        ${item.type === 'pass' ? '✓' : item.type === 'warn' ? '!' : '✗'}
                    </div>
                    <div class="check-text">
                        <div class="title">${item.message}</div>
                        ${item.details ? `<div class="detail">${item.details}</div>` : ''}
                        ${item.fix ? `<div class="fix"><strong>Fix:</strong> ${item.fix}</div>` : ''}
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

// Scan form handler
document.getElementById('scanForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const domain = document.getElementById('domainInput').value.trim();
    const biz = document.getElementById('bizInput').value.trim();
    const city = document.getElementById('cityInput').value.trim();
    
    if (!domain) return;
    
    const btn = document.getElementById('scanBtn');
    btn.disabled = true;
    btn.textContent = 'Scanning...';
    
    document.getElementById('status-bar').style.display = 'block';
    document.getElementById('progress-bar').style.display = 'block';
    document.getElementById('progress-bar').style.width = '10%';
    
    try {
        // Simulate progress
        let prog = 10;
        const progInterval = setInterval(() => {
            prog = Math.min(85, prog + Math.random() * 8);
            document.getElementById('progress-bar').style.width = prog + '%';
        }, 800);
        
        const resp = await fetch('/api/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ domain, business_name: biz, city }),
        });
        
        clearInterval(progInterval);
        document.getElementById('progress-bar').style.width = '100%';
        
        const data = await resp.json();
        
        if (data.error) {
            document.getElementById('statusText').textContent = 'Error: ' + data.error;
            setTimeout(() => {
                document.getElementById('status-bar').style.display = 'none';
                document.getElementById('progress-bar').style.display = 'none';
            }, 3000);
        } else {
            document.getElementById('statusText').textContent = 'Scan complete!';
            setTimeout(() => {
                document.getElementById('status-bar').style.display = 'none';
                document.getElementById('progress-bar').style.display = 'none';
            }, 1000);
            renderResults(data);
        }
    } catch (err) {
        document.getElementById('statusText').textContent = 'Error: ' + err.message;
        setTimeout(() => {
            document.getElementById('status-bar').style.display = 'none';
            document.getElementById('progress-bar').style.display = 'none';
        }, 3000);
    }
    
    btn.disabled = false;
    btn.textContent = 'Scan Now';
});
</script>
</body>
</html>
"""


# ====== ROUTES ======

@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)


@app.route("/api/scan", methods=["POST"])
def scan():
    data = request.get_json()
    domain = data.get("domain", "").strip()
    business_name = data.get("business_name", "").strip()
    city = data.get("city", "").strip()

    if not domain:
        return jsonify({"error": "Domain is required"}), 400

    # Clean domain
    if not domain.startswith(("http://", "https://")):
        domain = "https://" + domain

    try:
        result = scan_domain(domain, business_name, city)

        # Save to history for trend tracking
        clean_domain = domain.replace("https://", "").replace("http://", "").rstrip("/")
        save_history(clean_domain, result)

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/history/<path:domain>")
def history(domain):
    history = load_history()
    domain = domain.lower().strip()
    # Try exact match first
    data = history.get(domain)
    if data is None:
        # Try with/without www
        alt = domain.replace("www.", "", 1) if domain.startswith("www.") else "www." + domain
        data = history.get(alt)
    return jsonify(data or [])


@app.route("/api/status")
def status():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"AI Visibility Dashboard running at http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
