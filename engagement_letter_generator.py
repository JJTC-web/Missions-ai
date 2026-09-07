"""
Generates a Fund Development Engagement Letter PDF scoped to one specific
grant, mirroring the section structure of Jehovah Jireh Tax Consultants'
standard Fund Development Engagement Letter (Purpose, Scope of Services,
Fees, Client Responsibilities, Term & Termination, No Guarantee of
Funding, Acceptance) -- narrowed from "full fund development support" to
writing one named grant application.

Uses fpdf2 (pure Python, no system dependencies), so it renders the same
in local dev and on Railway.
"""

from datetime import date

from fpdf import FPDF

FIRM_NAME = "Jehovah Jireh Tax Consultants"
FIRM_TAGLINE = "Faith-Filled Financial Strategist"
FIRM_CONTACT = "www.jjtc.info | 254-589-5683 | info@jehovahjirehtaxconsultants.com"
FIRM_SIGNATORY = "Lady Emily, Jehovah Jireh Tax Consultants"

DEFAULT_FLAT_FEE = 200.00
DEFAULT_BONUS_PERCENT = 5


def _mc(pdf, text, h=6, **kwargs):
    """multi_cell wrapper that always returns the cursor to the left
    margin -- this fpdf2 build's default leaves x at the right margin
    after a full-width multi_cell, which then starves the next call of
    horizontal space."""
    pdf.multi_cell(0, h, text, new_x="LMARGIN", new_y="NEXT", **kwargs)


class _LetterPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 8, FIRM_NAME, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 10)
        self.cell(0, 6, FIRM_TAGLINE, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 5, FIRM_CONTACT, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.cell(0, 8, FIRM_CONTACT, align="C")


def _section(pdf, number, title, body_lines):
    pdf.set_font("Helvetica", "B", 12)
    _mc(pdf, f"{number}. {title}", h=7)
    pdf.set_font("Helvetica", "", 11)
    for line in body_lines:
        if line.startswith("- "):
            _mc(pdf, f"     - {line[2:]}")
        else:
            _mc(pdf, line)
    pdf.ln(2)


def generate_grant_engagement_letter_pdf(
    org_name,
    grant_name,
    grant_funder,
    client_rep_name,
    client_rep_title,
    flat_fee=DEFAULT_FLAT_FEE,
    bonus_percent=DEFAULT_BONUS_PERCENT,
    engagement_date=None,
):
    """Returns PDF bytes for a grant-specific Fund Development Engagement
    Letter, ready to attach to an org's Documents and sign in the portal.
    """
    engagement_date = engagement_date or date.today()
    funder_clause = f" from {grant_funder}" if grant_funder else ""

    pdf = _LetterPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 13)
    _mc(pdf, "FUND DEVELOPMENT ENGAGEMENT LETTER", h=8, align="C")
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 11)
    _mc(pdf, f"Date: {engagement_date.strftime('%B %d, %Y')}")
    _mc(pdf, f"Client Organization: {org_name}")
    _mc(pdf, f"Client Representative: {client_rep_name or '_______________________'}")
    _mc(pdf, f"Grant: {grant_name}{funder_clause}")
    pdf.ln(3)

    _section(pdf, 1, "Purpose of This Engagement", [
        f'Jehovah Jireh Tax Consultants ("JJTC," "we," or "us") is pleased to '
        f'provide grant-writing services to {org_name} ("Client" or "you") for its '
        f"{grant_name} grant application{funder_clause}. This letter outlines the scope of "
        "services, fees, and mutual expectations for this engagement.",
    ])

    _section(pdf, 2, "Scope of Services", [
        f"Grant-writing support for {org_name}'s {grant_name} grant application{funder_clause}, "
        "including:",
        f"- Review of eligibility and requirements for the {grant_name} grant",
        "- Grant application development and narrative writing",
        "- Assembly of required supporting documents and budget materials",
        "- Submission support and confirmation of receipt",
    ])

    _section(pdf, 3, "Fees", [
        "In recognition of Client's current budget constraints, JJTC agrees to the following "
        "reduced fee structure for this engagement:",
        f"- Nominal Flat Fee: ${flat_fee:,.2f} due upon signing of this agreement, covering the "
        "scope of services described in Section 2.",
        f"- Grant Success Bonus: An additional bonus of {bonus_percent:g}% of any grant funds "
        "awarded as a direct result of JJTC's assistance, due within 15 days of Client's receipt "
        "of such grant funds -- unless the terms of this grant prohibit percentage-based or "
        "contingency compensation to fundraising consultants, in which case JJTC and Client will "
        "agree upon an alternative flat fee for this grant prior to submission.",
        "This fee structure reflects a reduced rate extended as a courtesy given Client's stated "
        "budget limitations and does not reflect JJTC's standard fund development pricing.",
    ])

    _section(pdf, 4, "Client Responsibilities", [
        "- Provide timely access to organizational documents needed for this grant application "
        "(e.g., 501(c)(3) determination letter, budgets, board list)",
        "- Respond to requests for information within a reasonable timeframe",
        "- Approve the final grant application before submission",
    ])

    _section(pdf, 5, "Term & Termination", [
        "This engagement begins on the date this letter is signed and continues until the "
        "services described in Section 2 are complete, or until terminated in writing by either "
        "party with 15 days' notice. The Grant Success Bonus described in Section 3 remains "
        "payable for any grant funds awarded because of work performed during the engagement, "
        "even if the engagement has since ended.",
    ])

    _section(pdf, 6, "No Guarantee of Funding", [
        "JJTC will apply its professional expertise and best efforts to support Client's "
        f"application for the {grant_name} grant. However, JJTC does not guarantee that any "
        "specific grant, sponsorship, or funding outcome will be achieved.",
    ])

    _section(pdf, 7, "Acceptance", [
        "By signing below, Client agrees to engage Jehovah Jireh Tax Consultants under the "
        "terms described in this letter.",
    ])

    pdf.ln(10)
    pdf.cell(90, 6, "Client Signature", border="T")
    pdf.cell(10, 6, "")
    pdf.cell(0, 6, "Date", border="T", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.cell(90, 6, client_rep_name or "", border="T")
    pdf.cell(10, 6, "")
    pdf.cell(0, 6, client_rep_title or "", border="T", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(12)
    pdf.cell(90, 6, FIRM_SIGNATORY, border="T")
    pdf.cell(10, 6, "")
    pdf.cell(0, 6, "Date", border="T", new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
