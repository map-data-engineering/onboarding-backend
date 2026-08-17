"""
Upload and free-text rules for the final step.

These live server-side because that is the only place they hold. `accept=".pdf"`
on the file input and `maxlength` on a textarea are conveniences for the person
filling the form; the finalize endpoint is open, so anything that actually
matters has to be checked here.
"""

import re

from django.core.exceptions import ValidationError

# --- CV upload ---------------------------------------------------------------
CV_MAX_BYTES = 5 * 1024 * 1024   # 5 MB
CV_MAX_PAGES = 2
PDF_MAGIC = b"%PDF-"


def _human(size):
    return f"{size / (1024 * 1024):.1f} MB"


def validate_cv(uploaded):
    """
    A CV must be a real PDF, at most 5 MB, at most 2 pages.

    Checked in that order deliberately: size first (cheapest, and the only one
    that is a denial-of-service risk), then the magic bytes, then the page count
    -- there is no point parsing a 200 MB upload to discover it is a .zip.
    """
    if uploaded is None:
        raise ValidationError("Please attach your CV.")

    size = getattr(uploaded, "size", None)
    if size is not None and size > CV_MAX_BYTES:
        raise ValidationError(
            f"Your CV is {_human(size)}. The limit is {_human(CV_MAX_BYTES)} — "
            f"please save it at a lower quality or export it as a smaller PDF."
        )
    if size == 0:
        raise ValidationError("That file is empty.")

    name = (getattr(uploaded, "name", "") or "").lower()
    if not name.endswith(".pdf"):
        raise ValidationError("Your CV must be a PDF. Word documents are not accepted.")

    # The extension is a claim; the first bytes are evidence. A renamed .docx
    # would sail past an extension check alone.
    head = uploaded.read(len(PDF_MAGIC))
    uploaded.seek(0)
    if head != PDF_MAGIC:
        raise ValidationError(
            "That file is not a PDF, despite the .pdf name. Please export a real PDF."
        )

    pages = _page_count(uploaded)
    if pages is None:
        raise ValidationError(
            "We could not read that PDF — it may be damaged or password-protected. "
            "Please re-export it and try again."
        )
    if pages > CV_MAX_PAGES:
        raise ValidationError(
            f"Your CV is {pages} pages. Please shorten it to {CV_MAX_PAGES} pages or fewer."
        )
    return uploaded


def _page_count(uploaded):
    """Number of pages, or None if the file cannot be parsed."""
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        uploaded.seek(0)
        reader = PdfReader(uploaded)
        if reader.is_encrypted:
            # Some PDFs are "encrypted" with an empty owner password, which is
            # readable; a real password is not, and we reject that.
            try:
                if reader.decrypt("") == 0:
                    return None
            except (NotImplementedError, PyPdfError):
                return None
        return len(reader.pages)
    except (PyPdfError, OSError, ValueError, RecursionError):
        return None
    finally:
        try:
            uploaded.seek(0)   # leave the handle where Django expects it
        except (OSError, ValueError):
            pass


# --- Phone -------------------------------------------------------------------
# Spaces, hyphens, brackets and dots are all fine to type; they are stripped
# before counting digits. ITU E.164 allows up to 15 digits including the country
# code, and no real number is shorter than 7 after it.
_PHONE_PUNCTUATION = re.compile(r"[\s\-().]")
PHONE_MIN_DIGITS = 8
PHONE_MAX_DIGITS = 15


def validate_phone(value):
    """
    A number we can actually dial from outside the applicant's country.

    The leading + is required, and the error says why rather than just refusing:
    a local number like 0712345678 looks completely correct to the person typing
    it, and the last round produced a list of shortlisted applicants whose
    numbers could not be called from abroad.
    """
    raw = (value or "").strip()
    if not raw:
        raise ValidationError("Please give a phone number, including the country code.")

    cleaned = _PHONE_PUNCTUATION.sub("", raw)
    if not cleaned.startswith("+"):
        raise ValidationError(
            "Please start with + and your country code, e.g. +255 712 345 678. "
            "A number beginning 0 cannot be dialled from outside your country."
        )

    digits = cleaned[1:]
    if not digits.isdigit():
        raise ValidationError(
            "Use digits only after the country code (spaces, hyphens and brackets are fine)."
        )
    if not PHONE_MIN_DIGITS <= len(digits) <= PHONE_MAX_DIGITS:
        raise ValidationError(
            f"That is {len(digits)} digits after the +. A full international number "
            f"has between {PHONE_MIN_DIGITS} and {PHONE_MAX_DIGITS}."
        )
    return raw


# --- Free text ---------------------------------------------------------------
MAX_WORDS = 300


def count_words(text):
    """Whitespace-delimited word count — the same thing a person would count."""
    return len(re.findall(r"\S+", text or ""))


def validate_word_limit(text, limit=MAX_WORDS, label="This answer"):
    words = count_words(text)
    if words > limit:
        raise ValidationError(
            f"{label} is {words} words. Please shorten it to {limit} words or fewer."
        )
    return text
