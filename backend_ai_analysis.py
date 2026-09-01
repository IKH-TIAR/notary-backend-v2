"""
backend_ai_analysis.py
======================
Analyzes a PDF using Gemini to detect all signature / initials / date fields,
returning a structured AnalysisResult dict to store in ProjectDocument.analysis.

REQUIREMENTS
------------
    pip install google-genai

ENVIRONMENT
-----------
    GEMINI_API_KEY=<your key>
"""

import base64
import json
import os
from pathlib import Path

from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Read lazily inside each function so a server restart always picks up the
# current value from os.environ (populated by django-environ from .env).
def _get_api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL   = "gemini-3.1-pro-preview"


# ---------------------------------------------------------------------------
# Response schema (mirrors the TypeScript types on the frontend)
# ---------------------------------------------------------------------------
ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "documentType": {"type": "string"},
        "documentDescription": {"type": "string"},
        "summary": {"type": "string"},
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id":        {"type": "string"},
                    "label":     {"type": "string"},
                    "isSigned":  {"type": "boolean"},
                    "page":      {"type": "integer"},
                    "reasoning": {"type": "string"},
                    "box": {
                        "type": "object",
                        "properties": {
                            "ymin": {"type": "integer"},
                            "xmin": {"type": "integer"},
                            "ymax": {"type": "integer"},
                            "xmax": {"type": "integer"},
                        },
                        "required": ["ymin", "xmin", "ymax", "xmax"],
                    },
                },
                "required": ["id", "label", "isSigned", "page", "box"],
            },
        },
    },
    "required": ["documentType", "documentDescription", "summary", "fields"],
}

PROMPT = """
You are an expert document forensic analyst and estate planning specialist.
Your task has TWO parts:

--- PART 1: DOCUMENT IDENTIFICATION ---
Read the full document and identify:

1. "documentType": The official name/title of this document. Choose the best
   match from the list below, or use the actual title if it does not match:
   - Master Trust / Living Trust / Revocable Trust
   - Pour-Over Will
   - Durable Power of Attorney
   - Advance Health Care Directive
   - Certification of Trust
   - Grant Deed
   - HIPAA Authorization
   - Assignment of Personal Property
   - Trust Amendment

2. "documentDescription": A short, plain-language explanation of what this
   document does and why it matters to the client. Write it in a warm,
   conversational tone as if explaining to someone with no legal background.
   Base the description on the actual content of this document.
   Examples of tone:
   - Master Trust: "This is the main 'bucket' for your assets; it lets you
     manage everything while you're here and makes sure it all goes exactly
     where you want it later."
   - Pour-Over Will: "Think of this as a safety net — it catches anything
     you might have missed putting into your trust and 'pours' it back in
     so your plan stays complete."
   Write a similarly warm 1-3 sentence description specific to this document.

--- PART 2: FIELD DETECTION ---
Perform a highly detailed scan to identify ALL fields requiring user input
(signatures, initials, dates, checkmarks, text boxes).

CRITICAL ACCURACY INSTRUCTIONS:
1. Page-by-Page Analysis: Examine every page. Do not skip any.
2. Inline Text Fields: Scan all paragraphs for underscores (_______),
   brackets ([ ]), or spaces explicitly reserved for data entry within a sentence.
3. Table Analysis: Identify cells that act as signature boxes, initials fields,
   or date fields.
4. Contextual Clues: Look for labels like "Signed:", "By:", "Date:", "Initials:", etc.
5. Coordinate System: The bounding box must use a 0-1000 scale where
   (0,0) is the top-left and (1000,1000) is the bottom-right of the page.
6. isSigned: set to true ONLY if the field already contains a visible
   signature, initials, date, or handwritten/typed value. Otherwise false.

Output a JSON object with:
- "documentType":        the document title (from Part 1)
- "documentDescription": the plain-language explanation (from Part 1)
- "summary":             a short human-readable summary (e.g. "5 fields found, 3 unsigned")
- "fields":              array of field objects as described above
"""


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------
def analyze_pdf(pdf_source: "str | Path | bytes", file_name: str = "document.pdf") -> dict:
    """
    Analyze a PDF with Gemini and return an AnalysisResult dict.

    Parameters
    ----------
    pdf_source : str | Path | bytes
        Either a file path (str / Path) or raw PDF bytes.
    file_name : str
        The display name sent back to the frontend as `fileName`.

    Returns
    -------
    dict  matching AnalysisResult shape:
        {
            "fileName":            str,
            "documentType":        str,
            "documentDescription": str,
            "summary":             str,
            "fields":              list[dict]
        }
    """
    api_key = _get_api_key()
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY is not set")

    if isinstance(pdf_source, (str, Path)):
        pdf_bytes = Path(pdf_source).read_bytes()
    else:
        pdf_bytes = pdf_source

    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=types.Content(
            parts=[
                types.Part(
                    inline_data=types.Blob(
                        mime_type="application/pdf",
                        data=pdf_b64,
                    )
                ),
                types.Part(text=PROMPT),
            ]
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ANALYSIS_SCHEMA,
        ),
    )

    raw = json.loads(response.text or "{}")

    return {
        "fileName":            file_name,
        "documentType":        raw.get("documentType", ""),
        "documentDescription": raw.get("documentDescription", ""),
        "summary":             raw.get("summary", ""),
        "fields":              raw.get("fields", []),
    }


# ---------------------------------------------------------------------------
# Refine a single manually-drawn field (used for "Add Manual" in the viewer)
# ---------------------------------------------------------------------------
REFINE_SCHEMA = {
    "type": "object",
    "properties": {
        "label":     {"type": "string"},
        "isSigned":  {"type": "boolean"},
        "reasoning": {"type": "string"},
    },
    "required": ["label", "isSigned"],
}


def refine_field(
    pdf_source: "str | Path | bytes",
    page_number: int,
    box: dict,
) -> dict:
    """
    Given coordinates of a manually-drawn box on a specific page,
    ask Gemini to identify and label the field.

    Parameters
    ----------
    pdf_source  : str | Path | bytes
    page_number : int   (1-based)
    box         : dict  { ymin, xmin, ymax, xmax }  — 0-1000 scale

    Returns
    -------
    dict { "label": str, "isSigned": bool, "reasoning": str }
    """
    api_key = _get_api_key()
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY is not set")

    if isinstance(pdf_source, (str, Path)):
        pdf_bytes = Path(pdf_source).read_bytes()
    else:
        pdf_bytes = pdf_source

    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    refine_prompt = f"""
A user has manually highlighted an area on page {page_number} of this PDF.
The coordinates (0-1000 scale) are:
  ymin={box['ymin']}, xmin={box['xmin']}, ymax={box['ymax']}, xmax={box['xmax']}

Your task:
1. Identify what this field is (e.g. "Signature", "Initials", "Date").
2. Determine if it is currently signed/filled (isSigned: true) or empty (isSigned: false).
3. Provide a brief label based on surrounding text (e.g. "Page {page_number} Witness Signature").

Return ONLY a JSON object: {{ "label": "...", "isSigned": bool, "reasoning": "..." }}
"""

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=types.Content(
            parts=[
                types.Part(
                    inline_data=types.Blob(mime_type="application/pdf", data=pdf_b64)
                ),
                types.Part(text=refine_prompt),
            ]
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=REFINE_SCHEMA,
        ),
    )

    return json.loads(response.text or "{}")


# ---------------------------------------------------------------------------
# Verify a signed hardcopy PDF against user-claimed field statuses
# ---------------------------------------------------------------------------
VERIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string"},          # "completed" | "needs_fix"
        "signed_count":   {"type": "integer"},
        "total_count":    {"type": "integer"},
        "field_results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id":                 {"type": "string"},
                    "label":              {"type": "string"},
                    "user_claimed_signed": {"type": "boolean"},
                    "actually_signed":    {"type": "boolean"},
                    "match":              {"type": "boolean"},
                    "note":               {"type": "string"},
                },
                "required": ["id", "label", "user_claimed_signed", "actually_signed", "match"],
            },
        },
    },
    "required": ["status", "signed_count", "total_count", "field_results"],
}


def verify_signed_pdf(
    hardcopy_source: "str | Path | bytes",
    original_fields: list,
    user_fields: list,
) -> dict:
    """
    Cross-verify a user-uploaded hardcopy PDF against what the user claimed
    was signed, and what the original AI analysis detected.

    Parameters
    ----------
    hardcopy_source : str | Path | bytes
        The scanned/signed PDF uploaded by the user.
    original_fields : list
        The ``fields`` array from the original AI analysis
        (each item: { id, label, page, box, isSigned, ... }).
    user_fields : list
        The user's tap-confirmed statuses
        (each item: { id, isSigned }).

    Returns
    -------
    dict  {
        "status":        "completed" | "needs_fix",
        "signed_count":  int,
        "total_count":   int,
        "label":         str,   e.g. "4 of 5 signed correctly"
        "field_results": list[dict]
    }
    """
    api_key = _get_api_key()
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY is not set")

    if isinstance(hardcopy_source, (str, Path)):
        pdf_bytes = Path(hardcopy_source).read_bytes()
    else:
        pdf_bytes = hardcopy_source

    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    # Build a readable field list for the prompt
    field_lines = []
    user_map = {f["id"]: f.get("isSigned", False) for f in user_fields}
    for f in original_fields:
        fid     = f["id"]
        label   = f["label"]
        page    = f["page"]
        box     = f["box"]
        reasoning = f.get("reasoning", "")
        claimed = user_map.get(fid, f.get("isSigned", False))
        field_lines.append(
            f'  - id="{fid}" label="{label}" page={page} '
            f'box={{ymin:{box["ymin"]},xmin:{box["xmin"]},ymax:{box["ymax"]},xmax:{box["xmax"]}}} '
            f'context="{reasoning}" '
            f'user_claimed_signed={claimed}'
        )

    fields_text = "\n".join(field_lines)

    verify_prompt = f"""
You are an expert document verifier.
The user has uploaded a scanned or printed hardcopy PDF of a legal document they have physically signed.

IMPORTANT: The hardcopy may have been printed on different paper, scanned at a different resolution,
or have slightly different margins/formatting compared to the original digital document.
DO NOT rely solely on bounding box coordinates — they are approximate hints only.

YOUR PRIMARY APPROACH for finding each field:
1. Use the field LABEL (e.g. "Grantor Signature", "Witness Initials", "Date") and the CONTEXT
   text surrounding it to locate the field visually on the correct page.
2. Use the bounding box (0-1000 scale) only as a rough spatial hint to narrow down the area.
3. Look for the field by its label text, nearby printed words, lines, or signature blocks
   that match the context description.

Fields to verify:
{fields_text}

For EACH field:
- Locate it on the specified page using the label + context text (bounding box is a hint).
- Determine whether a real handwritten signature, initials, date, checkmark, or typed value
  is ACTUALLY present at that location in the hardcopy.
- Set "actually_signed": true ONLY if you can see a real filled value there.
- Set "match": true if user_claimed_signed == actually_signed.
- Set "note": a brief remark explaining what you saw (e.g. "Signature clearly visible",
  "Field is blank — no signature found near this label", "Date written in blue ink").

OUTPUT RULES:
- "signed_count": total fields where actually_signed is true.
- "total_count": total number of fields.
- "status": "completed" if ALL fields are actually_signed=true, otherwise "needs_fix".
"""

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=types.Content(
            parts=[
                types.Part(
                    inline_data=types.Blob(mime_type="application/pdf", data=pdf_b64)
                ),
                types.Part(text=verify_prompt),
            ]
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VERIFICATION_SCHEMA,
        ),
    )

    raw = json.loads(response.text or "{}")
    signed  = raw.get("signed_count", 0)
    total   = raw.get("total_count", len(original_fields))
    vstatus = raw.get("status", "needs_fix")

    return {
        "status":        vstatus,
        "signed_count":  signed,
        "total_count":   total,
        "label":         f"{signed} of {total} signed correctly",
        "field_results": raw.get("field_results", []),
    }


# ---------------------------------------------------------------------------
# Quick local test  (python backend_ai_analysis.py sample.pdf)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python backend_ai_analysis.py <path/to/file.pdf>")
        sys.exit(1)

    result = analyze_pdf(sys.argv[1], file_name=Path(sys.argv[1]).name)
    print(json.dumps(result, indent=2))
