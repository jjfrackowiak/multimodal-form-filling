# ruff: noqa: E501
"""HTML bodies for client-facing mail.

Plaintext `OutboundMessage.body` stays the contract Janek's golden tests assert.
This module only produces `html_body`: table layout, inline CSS, a 600px card that
collapses to full-width on a phone. Gmail/Outlook do not run modern CSS — flex, grid
and `<style>` in `<head>` are best-effort; every visual that matters is on the tag.
"""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence

from mff_contracts import RequestResult, Requirement, ReviewComment

__all__ = ["render_confirmation_html", "render_delivery_html", "render_rejection_html"]

_OK_VERDICTS = frozenset({"pass", "realised", "not_applicable"})
_ATTENTION_VERDICTS = frozenset({"fail", "shortfall"})
_VERDICT_LABELS_PL = {
    "pass": "spełnionych",
    "fail": "niespełnionych",
    "unverified": "niezweryfikowanych",
}
_MODE_HEADING_PL = {
    "derivative": "sprawdzone formularze (derivative)",
    "net_new": "utworzone dokumenty (net-new)",
    "dokument": "dokumenty",
}

# Warm paper + stone. Reads on a phone in daylight; not a dark-mode experiment.
_BG = "#f3efe6"
_CARD = "#ffffff"
_INK = "#1c1917"
_MUTED = "#57534e"
_LINE = "#e7e5e4"
_FAIL = "#9f1239"
_FAIL_BG = "#fff1f2"
_PASS = "#166534"
_PASS_BG = "#f0fdf4"
_WARN = "#9a3412"
_WARN_BG = "#fff7ed"
_NAVY = "#1c1917"


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def _br(value: str) -> str:
    return _esc(value).replace("\n", "<br>")


def _wrap(*, title: str, preheader: str, inner: str) -> str:
    """Shell: viewport, 100% outer table, 600px inner card, stacked padding on mobile."""
    return f"""\
<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<meta http-equiv="x-ua-compatible" content="ie=edge">
<title>{_esc(title)}</title>
<style>
  html, body {{ margin: 0 !important; padding: 0 !important; width: 100% !important; }}
  * {{ -ms-text-size-adjust: 100%; -webkit-text-size-adjust: 100%; }}
  table, td {{ mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
  img {{ -ms-interpolation-mode: bicubic; border: 0; }}
  @media only screen and (max-width: 620px) {{
    .wrapper {{ width: 100% !important; max-width: 100% !important; }}
    .px {{ padding-left: 16px !important; padding-right: 16px !important; }}
    .stat {{
      display: block !important;
      width: 100% !important;
      border-right: 0 !important;
      border-bottom: 1px solid {_LINE} !important;
    }}
    .stat:last-child {{ border-bottom: 0 !important; }}
    .chip {{ display: inline-block !important; margin: 0 6px 8px 0 !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:{_BG};width:100%;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
    {_esc(preheader)}
  </div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_BG};width:100%;">
    <tr>
      <td align="center" style="padding:16px 8px;">
        <table role="presentation" class="wrapper" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:100%;background:{_CARD};border-radius:12px;overflow:hidden;border:1px solid {_LINE};">
          {inner}
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def _header(kicker: str, heading: str, badge: str, badge_bg: str) -> str:
    return f"""\
<tr>
  <td class="px" style="background:{_NAVY};padding:20px 24px;">
    <p style="margin:0 0 8px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:#a8a29e;">
      {_esc(kicker)}
    </p>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:20px;line-height:1.3;font-weight:650;color:#fff;padding-right:12px;">
          {_esc(heading)}
        </td>
        <td valign="top" align="right" style="white-space:nowrap;">
          <span style="display:inline-block;padding:4px 10px;border-radius:999px;background:{badge_bg};color:#fff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:12px;font-weight:600;">
            {_esc(badge)}
          </span>
        </td>
      </tr>
    </table>
  </td>
</tr>
"""


def _footer() -> str:
    return f"""\
<tr>
  <td class="px" style="padding:16px 24px 24px;border-top:1px solid {_LINE};">
    <p style="margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:12px;line-height:1.5;color:{_MUTED};">
      Form Validation — wiadomość wygenerowana automatycznie
    </p>
  </td>
</tr>
"""


def _p(text: str, *, muted: bool = False) -> str:
    color = _MUTED if muted else _INK
    return (
        f'<p style="margin:0 0 12px;font-family:-apple-system,BlinkMacSystemFont,'
        f"'Segoe UI',Roboto,sans-serif;font-size:16px;line-height:1.55;color:{color};\">"
        f"{text}</p>"
    )


def _h2(text: str) -> str:
    return (
        f'<p style="margin:20px 0 10px;font-family:-apple-system,BlinkMacSystemFont,'
        f"'Segoe UI',Roboto,sans-serif;font-size:11px;letter-spacing:0.14em;"
        f'text-transform:uppercase;color:{_MUTED};font-weight:700;">{_esc(text)}</p>'
    )


def _stat_cell(count: int, label: str, color: str, *, last: bool) -> str:
    border = "0" if last else f"1px solid {_LINE}"
    return f"""\
<td class="stat" width="33%" valign="top" style="width:33%;padding:14px 8px;text-align:center;border-right:{border};">
  <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:28px;line-height:1.1;font-weight:700;color:{color};">{count}</div>
  <div style="margin-top:4px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:12px;color:{_MUTED};">{_esc(label)}</div>
</td>
"""


def _summary_row(result: RequestResult) -> str:
    n_pass = sum(result.summary.get(k, 0) for k in ("pass", "realised", "not_applicable"))
    n_fail = sum(result.summary.get(k, 0) for k in ("fail", "shortfall"))
    n_unverified = len(result.unverified)
    cells = [
        _stat_cell(n_pass, _VERDICT_LABELS_PL.get("pass", "spełnionych"), _PASS, last=False),
        _stat_cell(n_fail, _VERDICT_LABELS_PL.get("fail", "niespełnionych"), _FAIL, last=False),
        _stat_cell(
            n_unverified,
            _VERDICT_LABELS_PL.get("unverified", "niezweryfikowanych"),
            _WARN,
            last=True,
        ),
    ]
    return f"""\
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:8px 0 16px;border:1px solid {_LINE};border-radius:10px;overflow:hidden;">
  <tr>
    {"".join(cells)}
  </tr>
</table>
"""


def _fail_card(comment: ReviewComment) -> str:
    suggestion = ""
    if comment.suggestion:
        suggestion = f"""\
<p style="margin:10px 0 0;padding:10px 12px;background:{_FAIL_BG};border-radius:8px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:14px;line-height:1.5;color:{_INK};">
  <strong style="color:{_FAIL};">Sugestia.</strong> {_br(comment.suggestion)}
</p>
"""
    return f"""\
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 12px;border:1px solid {_LINE};border-left:4px solid {_FAIL};border-radius:8px;">
  <tr>
    <td style="padding:14px 16px;">
      <p style="margin:0 0 6px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:13px;font-weight:700;color:{_FAIL};">
        {_esc(comment.requirement_id)}
      </p>
      <p style="margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:15px;line-height:1.5;color:{_INK};word-break:break-word;">
        {_br(comment.justification)}
      </p>
      {suggestion}
    </td>
  </tr>
</table>
"""


def _pass_chips(comments: Sequence[ReviewComment]) -> str:
    chips = []
    for comment in sorted(comments, key=lambda c: c.requirement_id):
        chips.append(
            f'<span class="chip" style="display:inline-block;margin:0 6px 8px 0;padding:6px 10px;'
            f"border-radius:999px;background:{_PASS_BG};color:{_PASS};font-family:-apple-system,"
            f"BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:13px;font-weight:650;\">"
            f"{_esc(comment.requirement_id)}</span>"
        )
    return "".join(chips)


def _unverified_block(result: RequestResult, requirements_by_id: Mapping[str, Requirement]) -> str:
    if not result.unverified:
        return ""
    rows = []
    for req_id in result.unverified:
        requirement = requirements_by_id.get(req_id)
        text = f" {_esc(requirement.text)}" if requirement else ""
        rows.append(
            f'<p style="margin:0 0 8px;font-family:-apple-system,BlinkMacSystemFont,'
            f"'Segoe UI',Roboto,sans-serif;font-size:15px;color:{_INK};\">"
            f"<strong>[{_esc(req_id)}]</strong>{text}</p>"
        )
    return (
        _h2("Niezweryfikowane")
        + _p(
            "System podjął trzy próby i nie zdołał ocenić poniższych wymagań. "
            "Prosimy traktować je jako nierozstrzygnięte, nie jako spełnione.",
            muted=True,
        )
        + "".join(rows)
    )


def _failed_forms_block(result: RequestResult) -> str:
    if result.status != "partial" or not result.failed_forms:
        return ""
    items = "".join(
        f'<p style="margin:0 0 6px;font-family:-apple-system,BlinkMacSystemFont,'
        f"'Segoe UI',Roboto,sans-serif;font-size:15px;color:{_INK};\">· {_esc(form_id)}</p>"
        for form_id in result.failed_forms
    )
    return (
        _h2("Nieukończone formularze")
        + _p("Poniższe formularze nie zostały ukończone i nie są dołączone.", muted=True)
        + items
    )


def _docs_block(
    attached: Sequence[tuple[str, str, int]],
    linked: Sequence[tuple[str, str, str]],
) -> str:
    """attached: (filename, mode, size_bytes). linked: (name, mode, url)."""
    if not attached and not linked:
        return ""
    modes_present = {mode for _, mode, _ in (*attached, *linked)}
    multi_mode = len(modes_present) > 1

    def _mode_heading(mode_label: str) -> str:
        if not multi_mode:
            return ""
        return _p(_esc(_MODE_HEADING_PL.get(mode_label, mode_label)), muted=True)

    parts: list[str] = []
    if attached:
        parts.append(_h2("Załączone dokumenty"))
        seen: list[str] = []
        for _filename, mode, _size in attached:
            if mode not in seen:
                seen.append(mode)
        for mode_label in seen:
            parts.append(_mode_heading(mode_label))
            for filename, mode, size_bytes in attached:
                if mode != mode_label:
                    continue
                kb = size_bytes / 1024
                parts.append(
                    f'<p style="margin:0 0 8px;font-family:-apple-system,BlinkMacSystemFont,'
                    f"'Segoe UI',Roboto,sans-serif;font-size:15px;color:{_INK};word-break:break-word;\">"
                    f"📎 {_esc(filename)} "
                    f'<span style="color:{_MUTED};">({kb:.0f} KB)</span></p>'
                )
    if linked:
        parts.append(_h2("Dokumenty pod linkiem"))
        parts.append(_p("Przekraczają limit załącznika — link ważny 7 dni.", muted=True))
        seen_l: list[str] = []
        for _name, mode, _url in linked:
            if mode not in seen_l:
                seen_l.append(mode)
        for mode_label in seen_l:
            parts.append(_mode_heading(mode_label))
            for name, mode, url in linked:
                if mode != mode_label:
                    continue
                parts.append(
                    f'<p style="margin:0 0 10px;font-family:-apple-system,BlinkMacSystemFont,'
                    f"'Segoe UI',Roboto,sans-serif;font-size:15px;word-break:break-all;\">"
                    f'<a href="{_esc(url)}" style="color:{_FAIL};">{_esc(name)}</a></p>'
                )
    return "".join(parts)


def _requirement_card(requirement: Requirement) -> str:
    extra = []
    extra.append(
        f'<p style="margin:6px 0 0;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;'
        f'font-size:13px;line-height:1.45;color:{_MUTED};word-break:break-word;">'
        f"wiersz {requirement.source_line}: „{_esc(requirement.source_span)}”</p>"
    )
    constraint = requirement.constraint
    if constraint is not None:
        extra.append(
            f'<p style="margin:6px 0 0;font-family:-apple-system,BlinkMacSystemFont,'
            f"'Segoe UI',Roboto,sans-serif;font-size:13px;color:{_INK};\">"
            f"warunek: {_esc(constraint.kind)} = {_esc(str(constraint.value))}<br>"
            f'<span style="color:{_MUTED};">wiersz {constraint.source_line}: '
            f"„{_esc(constraint.source_span)}”</span></p>"
        )
    if requirement.ambiguity:
        extra.append(
            f'<p style="margin:8px 0 0;padding:8px 10px;background:{_WARN_BG};border-radius:6px;'
            f"font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;"
            f'font-size:13px;color:{_WARN};">UWAGA: {_esc(requirement.ambiguity)}</p>'
        )
    return f"""\
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 10px;border:1px solid {_LINE};border-radius:8px;">
  <tr>
    <td style="padding:12px 14px;">
      <p style="margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:15px;line-height:1.45;color:{_INK};word-break:break-word;">
        <strong>{_esc(requirement.id)}</strong> · {_esc(requirement.text)}
      </p>
      {"".join(extra)}
    </td>
  </tr>
</table>
"""


def render_delivery_html(
    *,
    result: RequestResult,
    comments: Sequence[ReviewComment],
    attached: Sequence[tuple[str, str, int]],
    linked: Sequence[tuple[str, str, str]],
) -> str:
    requirements_by_id = {r.id: r for r in result.requirements}
    attention = [c for c in comments if c.verdict in _ATTENTION_VERDICTS]
    ok = [c for c in comments if c.verdict in _OK_VERDICTS]
    status_badge = {"done": "zakończone", "partial": "częściowo", "failed": "nieudane"}.get(
        result.status, result.status
    )
    badge_bg = {"done": _PASS, "partial": _WARN, "failed": _FAIL}.get(result.status, _MUTED)

    body_bits = [
        _p(
            f"Państwa zgłoszenie zostało sprawdzone względem "
            f"<strong>{len(result.requirements)}</strong> wymagań odczytanych z manifestu."
        ),
        _summary_row(result),
    ]
    if attention:
        body_bits.append(_h2("Niespełnione"))
        for comment in sorted(attention, key=lambda c: c.requirement_id):
            body_bits.append(_fail_card(comment))
    if ok:
        body_bits.append(_h2("Spełnione"))
        body_bits.append(_pass_chips(ok))
    body_bits.append(_unverified_block(result, requirements_by_id))
    body_bits.append(_failed_forms_block(result))
    body_bits.append(_docs_block(attached, linked))
    body_bits.append(_h2("Odczytane wymagania"))
    body_bits.append(
        _p(
            "Komentarze w załączonym dokumencie odwołują się do tych numerów. "
            "Przy każdym podano fragment Państwa manifestu.",
            muted=True,
        )
    )
    for requirement in sorted(result.requirements, key=lambda r: (r.ordinal, r.text)):
        body_bits.append(_requirement_card(requirement))
    body_bits.append(
        _p(
            "Pełne uzasadnienia znajdują się w komentarzach recenzenta w załączonym "
            "dokumencie Word (panel Recenzja).",
            muted=True,
        )
    )

    inner = (
        _header(
            kicker="Form Validation",
            heading=f"Wyniki weryfikacji · {result.request_id}",
            badge=status_badge,
            badge_bg=badge_bg,
        )
        + (f'<tr><td class="px" style="padding:24px;">{"".join(body_bits)}</td></tr>')
        + _footer()
    )

    n_fail = sum(result.summary.get(k, 0) for k in ("fail", "shortfall"))
    preheader = f"{status_badge}: {len(result.requirements)} wymagań, {n_fail} do poprawy."
    return _wrap(
        title=f"Wyniki weryfikacji — {result.request_id}", preheader=preheader, inner=inner
    )


def render_confirmation_html(
    *,
    request_id: str,
    n_derivative: int,
    n_net_new: int,
    n_jobs: int,
    requirements: Sequence[Requirement],
) -> str:
    cards = []
    for requirement in requirements:
        extra = ""
        if requirement.constraint is not None:
            extra += (
                f'<p style="margin:6px 0 0;font-size:13px;color:{_MUTED};">'
                f"constraint: {_esc(requirement.constraint.kind)} = "
                f"{_esc(str(requirement.constraint.value))}</p>"
            )
        cards.append(
            f'<p style="margin:0 0 10px;font-family:-apple-system,BlinkMacSystemFont,'
            f"'Segoe UI',Roboto,sans-serif;font-size:15px;line-height:1.45;color:{_INK};"
            f'word-break:break-word;"><strong>[{_esc(requirement.id)}]</strong> '
            f"{_esc(requirement.text)}<br>"
            f'<span style="color:{_MUTED};font-size:13px;">manifest line '
            f"{requirement.source_line}: „{_esc(requirement.source_span)}”</span>{extra}</p>"
        )
    inner = (
        _header(
            kicker="Form Validation",
            heading="Request accepted",
            badge="202",
            badge_bg=_PASS,
        )
        + f"""\
<tr>
  <td class="px" style="padding:24px;">
    {_p("Your request has been received and accepted.")}
    {_p(f"Request ID: <strong>{_esc(request_id)}</strong>")}
    {_p(f"{n_derivative} form(s) to validate, {n_net_new} form(s) to compose from supplied inputs ({n_jobs} job(s) total).", muted=True)}
    {_h2(f"{len(requirements)} requirement(s) from your manifest")}
    {"".join(cards)}
    {_p("The reviewed documents will follow in a separate email once every job has finished running.", muted=True)}
  </td>
</tr>
"""
        + _footer()
    )
    return _wrap(
        title="Request accepted",
        preheader=f"Accepted {request_id} — {len(requirements)} requirements.",
        inner=inner,
    )


def render_rejection_html(*, problems: Sequence[tuple[str, str]]) -> str:
    items = "".join(
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 10px;border:1px solid {_LINE};border-left:4px solid {_FAIL};border-radius:8px;"><tr><td style="padding:12px 14px;">'
        f"<p style=\"margin:0 0 4px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:12px;font-weight:700;color:{_FAIL};\">{_esc(code)}</p>"
        f"<p style=\"margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:15px;line-height:1.5;color:{_INK};word-break:break-word;\">{_br(detail)}</p>"
        f"</td></tr></table>"
        for code, detail in problems
    )
    inner = (
        _header(
            kicker="Form Validation",
            heading="Request could not be processed",
            badge="needs a fix",
            badge_bg=_FAIL,
        )
        + f"""\
<tr>
  <td class="px" style="padding:24px;">
    {_p("Please fix the following and resend:")}
    {items}
    {_p("No documents were reviewed and nothing was changed.", muted=True)}
  </td>
</tr>
"""
        + _footer()
    )
    return _wrap(
        title="Request could not be processed",
        preheader="Your request could not be processed — please fix and resend.",
        inner=inner,
    )
