"""
theme.py

Same dark-theme convention already used in FlightRisk and EvidenceRoute:
a dark background, styled cards instead of raw st.json() dumps, and an
accent color for numbers that matter.
"""

ACCENT = "#4ADE80"          # positive / recommended values
ACCENT_WARN = "#F97316"     # infeasible / warnings
BG = "#0E1117"
CARD_BG = "#1A1F2B"
BORDER = "#2A3140"

CSS = f"""
<style>
.stApp {{
    background-color: {BG};
}}
.mp-card {{
    background-color: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 1.1rem 1.3rem;
    margin-bottom: 0.9rem;
}}
.mp-card h4 {{
    margin: 0 0 0.6rem 0;
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #9CA3AF;
}}
.mp-metric {{
    font-size: 1.6rem;
    font-weight: 700;
    color: #F3F4F6;
}}
.mp-metric-accent {{
    color: {ACCENT};
}}
.mp-metric-warn {{
    color: {ACCENT_WARN};
}}
.mp-subtext {{
    color: #9CA3AF;
    font-size: 0.85rem;
}}
.mp-pill {{
    display: inline-block;
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    background-color: rgba(74, 222, 128, 0.15);
    color: {ACCENT};
}}
</style>
"""


def card(title: str, value: str, subtext: str = "", accent: str | None = None) -> str:
    cls = "mp-metric"
    if accent == "positive":
        cls += " mp-metric-accent"
    elif accent == "warn":
        cls += " mp-metric-warn"
    sub_html = f'<div class="mp-subtext">{subtext}</div>' if subtext else ""
    return f"""
    <div class="mp-card">
        <h4>{title}</h4>
        <div class="{cls}">{value}</div>
        {sub_html}
    </div>
    """
