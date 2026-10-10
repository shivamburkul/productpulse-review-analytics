import csv
import io
import json
from datetime import datetime

from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend import nlp_engine as nlp


def product_csv(a):
    out = io.StringIO()
    w = csv.writer(out, quoting=csv.QUOTE_ALL)
    feats = nlp.FEATURES
    w.writerow(["Product", "Reviews", "Positive", "Negative", "Neutral", "Mixed", "Positive %", "Negative %", "Average sentiment (-1 to +1)", "Average rating"]
               + ["%s sentiment" % f for f in feats] + ["Summary"])
    cell = {(c["product"], c["category"]): c["avg_score"] for c in a["category_by_product"]}
    for p in a["products"]:
        w.writerow([p["product"], p["total"], p["positive"], p["negative"], p["neutral"], p["mixed"], p["positive_pct"], p["negative_pct"], p["avg_score"],
                    "" if p.get("avg_rating") is None else p["avg_rating"]] + [cell.get((p["product"], f), "") for f in feats] + [a["summaries"][p["product"]]["text"]])
    return "\ufeff" + out.getvalue()


def analytics_json(a):
    return json.dumps(a, ensure_ascii=False, indent=1)


class _Numbered(canvas.Canvas):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._pages = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        for st in self._pages:
            self.__dict__.update(st)
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.grey)
            self.drawRightString(A4[0] - 18 * mm, 10 * mm, "Page %d of %d" % (self._pageNumber, len(self._pages)))
            self.drawString(18 * mm, 10 * mm, "ProductPulse report")
            super().showPage()
        super().save()


def pdf_bytes(a, filename):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm, title="ProductPulse Report")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=colors.HexColor("#1e3a8a"), fontSize=24)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=colors.HexColor("#1e3a8a"), spaceBefore=10)
    h3 = ParagraphStyle("h3", parent=ss["Heading3"], spaceBefore=8, spaceAfter=2)
    body = ParagraphStyle("b", parent=ss["BodyText"], leading=14)
    small = ParagraphStyle("s", parent=body, fontSize=8, textColor=colors.grey)
    o, ing = a["overall"], a["ingest"]
    st = [Paragraph("ProductPulse", h1), Paragraph("Review Analytics Report", ss["Heading3"]), Spacer(1, 6),
          Paragraph("Generated: %s<br/>Dataset: %s<br/>Reviews analysed: %d &nbsp;|&nbsp; Products: %d" % (datetime.now().strftime("%d %B %Y, %H:%M"), _e(filename), o["total"], o["products"]), body)]
    st += [Paragraph("Overall sentiment", h2)]
    t = Table([["Positive", "Negative", "Neutral", "Mixed", "Average score"],
               [o["positive"], o["negative"], o["neutral"], o["mixed"], "%+.3f" % o["avg_score"]]], hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .5, colors.lightgrey),
                           ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("FONTSIZE", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    st += [t, Spacer(1, 4), Paragraph("Score range: -1 (very negative) to +1 (very positive). Rows read: %d, rejected: %d, duplicates removed: %d." % (ing["rows_read"], ing["rejected"], a["spark"]["duplicates_removed"]), small)]
    prods = a["products"][:15]
    d = Drawing(170 * mm, max(60, 14 * len(prods) + 40))
    ch = HorizontalBarChart()
    ch.x, ch.y, ch.width, ch.height = 110, 15, 270, 14 * len(prods) + 10
    ch.data = [[p["positive_pct"] for p in reversed(prods)], [p["negative_pct"] for p in reversed(prods)]]
    ch.categoryAxis.categoryNames = [p["product"][:22] for p in reversed(prods)]
    ch.categoryAxis.labels.fontSize = 7
    ch.valueAxis.valueMin, ch.valueAxis.valueMax = 0, 100
    ch.valueAxis.labels.fontSize = 7
    ch.bars[0].fillColor, ch.bars[1].fillColor = colors.HexColor("#22c55e"), colors.HexColor("#ef4444")
    d.add(ch)
    st += [Paragraph("Positive and negative reviews by product (% of reviews; green = positive, red = negative)", h3), d]
    rows = [["Product", "Reviews", "Pos %", "Neg %", "Avg score"]] + [[Paragraph(_e(p["product"]), body), p["total"], p["positive_pct"], p["negative_pct"], "%+.3f" % p["avg_score"]] for p in a["products"]]
    t = Table(rows, repeatRows=1, colWidths=[75 * mm, 22 * mm, 22 * mm, 22 * mm, 25 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .4, colors.lightgrey),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]), ("FONTSIZE", (0, 0), (-1, -1), 9), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    st += [Paragraph("Product results", h2), t, PageBreak(), Paragraph("Product summaries", h2)]
    cell = {(c["product"], c["category"]): c for c in a["category_by_product"]}
    for p in a["products"]:
        ft = [["Feature", "Mentions", "Avg sentiment"]] + [[f, cell[(p["product"], f)]["count"], "%+.3f" % cell[(p["product"], f)]["avg_score"]] for f in nlp.FEATURES if (p["product"], f) in cell]
        block = [Paragraph(_e(p["product"]), h3), Paragraph(_e(a["summaries"][p["product"]]["text"]), body)]
        if len(ft) > 1:
            tt = Table(ft, hAlign="LEFT", colWidths=[45 * mm, 25 * mm, 30 * mm])
            tt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .3, colors.lightgrey), ("FONTSIZE", (0, 0), (-1, -1), 8), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0"))]))
            block += [Spacer(1, 3), tt]
        st.append(KeepTogether(block + [Spacer(1, 6)]))
    doc.build(st, canvasmaker=_Numbered)
    return buf.getvalue()


def _e(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
