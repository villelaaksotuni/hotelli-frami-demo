from __future__ import annotations

import html
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.path_prefix import build_request_app_path
from app.routes.admin_auth import require_admin_access
from app.services.prompt_store import PromptStoreSnapshot, PromptVersion, prompt_store

router = APIRouter()


@router.get("/admin/prompt", response_class=HTMLResponse)
async def admin_prompt_page(
    request: Request,
    admin_user: Annotated[str, Depends(require_admin_access)],
):
    del admin_user
    snapshot = prompt_store.get_snapshot()
    notice = request.query_params.get("notice")
    return _render_prompt_admin_response(request, snapshot, notice=notice)


@router.post("/admin/prompt/save")
async def save_admin_prompt(
    request: Request,
    admin_user: Annotated[str, Depends(require_admin_access)],
):
    form = await request.form()
    prompt = str(form.get("prompt") or "")
    opening_message = str(form.get("opening_message") or "")
    try:
        prompt_store.save_prompt(
            prompt,
            opening_message=opening_message,
            updated_by=admin_user,
        )
    except ValueError as exc:
        return _render_prompt_admin_response(
            request,
            prompt_store.get_snapshot(),
            notice=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse(
        url=_build_prompt_admin_notice_url(request, "Prompt saved."),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/prompt/reset")
async def reset_admin_prompt(
    request: Request,
    admin_user: Annotated[str, Depends(require_admin_access)],
):
    prompt_store.reset_to_default(updated_by=admin_user)
    return RedirectResponse(
        url=_build_prompt_admin_notice_url(request, "Prompt reset to the built-in default."),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/prompt/restore")
async def restore_admin_prompt(
    request: Request,
    admin_user: Annotated[str, Depends(require_admin_access)],
):
    form = await request.form()
    version_id = str(form.get("version_id") or "")
    try:
        prompt_store.restore_version(version_id, updated_by=admin_user)
    except KeyError:
        return _render_prompt_admin_response(
            request,
            prompt_store.get_snapshot(),
            notice="The selected prompt version no longer exists.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return RedirectResponse(
        url=_build_prompt_admin_notice_url(request, "Prompt restored from history."),
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _build_prompt_admin_notice_url(request: Request, notice: str) -> str:
    prompt_page_path = build_request_app_path(request, "/admin/prompt")
    return f"{prompt_page_path}?notice={quote(notice)}"


def _render_prompt_admin_response(
    request: Request,
    snapshot: PromptStoreSnapshot,
    *,
    notice: str | None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    return HTMLResponse(
        _render_prompt_admin_page(
            snapshot,
            notice=notice,
            save_action=build_request_app_path(request, "/admin/prompt/save"),
            reset_action=build_request_app_path(request, "/admin/prompt/reset"),
            restore_action=build_request_app_path(request, "/admin/prompt/restore"),
        ),
        status_code=status_code,
    )


def _render_prompt_admin_page(
    snapshot: PromptStoreSnapshot,
    *,
    notice: str | None,
    save_action: str,
    reset_action: str,
    restore_action: str,
) -> str:
    active_prompt = html.escape(snapshot.active_prompt)
    active_opening_message = html.escape(snapshot.active_opening_message)
    active_version = next(
        (version for version in snapshot.versions if version.id == snapshot.active_version_id),
        None,
    )
    active_status = (
        f"Active version: {html.escape(active_version.id)} saved at {html.escape(active_version.created_at)}"
        if active_version
        else "Using the built-in default prompt."
    )
    history_markup = _render_history(
        snapshot.versions,
        snapshot.active_version_id,
        restore_action=restore_action,
    )
    notice_markup = f'<div class="notice">{html.escape(notice)}</div>' if notice else ""

    return f"""
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Prompt Admin</title>
    <style>
      :root {{
        --bg: #f3efe8;
        --panel: #fffaf4;
        --ink: #2e231f;
        --muted: #6e625b;
        --line: #d9c8ba;
        --accent: #225f5b;
        --accent-soft: #e1f0ef;
        --warning: #a95b2a;
      }}

      * {{
        box-sizing: border-box;
      }}

      body {{
        margin: 0;
        font-family: Georgia, "Times New Roman", serif;
        color: var(--ink);
        background:
          radial-gradient(circle at top left, rgba(34, 95, 91, 0.12), transparent 24%),
          linear-gradient(180deg, #f7f3ed 0%, #f0e9df 100%);
      }}

      main {{
        width: min(1200px, calc(100vw - 32px));
        margin: 32px auto 48px;
        display: grid;
        gap: 24px;
      }}

      .panel {{
        background: rgba(255, 250, 244, 0.94);
        border: 1px solid var(--line);
        border-radius: 24px;
        padding: 24px;
        box-shadow: 0 18px 40px rgba(40, 26, 17, 0.08);
      }}

      h1, h2, h3, p {{
        margin-top: 0;
      }}

      .notice {{
        padding: 14px 16px;
        border-radius: 16px;
        background: var(--accent-soft);
        color: var(--accent);
        border: 1px solid rgba(34, 95, 91, 0.2);
      }}

      .status {{
        color: var(--muted);
      }}

      textarea {{
        width: 100%;
        min-height: 360px;
        padding: 16px;
        border-radius: 18px;
        border: 1px solid var(--line);
        background: #fffdf9;
        color: var(--ink);
        font: 14px/1.55 Consolas, "Courier New", monospace;
        resize: vertical;
      }}

      .actions {{
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        margin-top: 16px;
      }}

      button {{
        border: 1px solid rgba(46, 35, 31, 0.16);
        background: white;
        color: var(--ink);
        border-radius: 999px;
        padding: 10px 16px;
        font: inherit;
        cursor: pointer;
      }}

      button.primary {{
        background: var(--accent);
        color: white;
        border-color: var(--accent);
      }}

      .history {{
        display: grid;
        gap: 16px;
      }}

      .history-card {{
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 18px;
        background: rgba(255, 255, 255, 0.68);
      }}

      .history-card.active {{
        border-color: rgba(34, 95, 91, 0.4);
        background: rgba(225, 240, 239, 0.56);
      }}

      .meta {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px 14px;
        color: var(--muted);
        font-size: 0.95rem;
      }}

      .badge {{
        display: inline-flex;
        align-items: center;
        padding: 4px 10px;
        border-radius: 999px;
        background: rgba(34, 95, 91, 0.14);
        color: var(--accent);
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }}

      pre {{
        margin: 14px 0 0;
        padding: 16px;
        border-radius: 16px;
        background: #fffdf9;
        border: 1px solid rgba(46, 35, 31, 0.08);
        white-space: pre-wrap;
        word-break: break-word;
        font: 13px/1.55 Consolas, "Courier New", monospace;
      }}

      .empty {{
        color: var(--warning);
      }}

      form.inline {{
        margin-top: 14px;
      }}

      @media (max-width: 760px) {{
        main {{
          width: min(100vw - 18px, 100%);
          margin-top: 16px;
        }}

        .panel {{
          padding: 18px;
          border-radius: 18px;
        }}

        textarea {{
          min-height: 280px;
        }}
      }}
    </style>
  </head>
  <body>
    <main>
      <section class="panel">
        <h1>Prompt Admin</h1>
        <p class="status">{html.escape(active_status)}</p>
        {notice_markup}
      </section>

      <section class="panel">
        <h2>Active Prompt</h2>
        <p class="status">Edits saved here become the default system prompt and opening turn for new calls unless the request body passes its own <code>system_message</code> or <code>opening_message</code>.</p>
        <form method="post" action="{html.escape(save_action)}">
          <textarea name="prompt">{active_prompt}</textarea>
          <p class="status" style="margin-top: 16px;">Opening message instructions for the first assistant turn:</p>
          <textarea name="opening_message" style="min-height: 140px;">{active_opening_message}</textarea>
          <div class="actions">
            <button class="primary" type="submit">Save Prompt</button>
          </div>
        </form>
        <form method="post" action="{html.escape(reset_action)}" class="inline">
          <button type="submit">Reset To Built-In Default</button>
        </form>
      </section>

      <section class="panel">
        <h2>Saved Prompt History</h2>
        <p class="status">Every saved or restored prompt version stays visible here.</p>
        <div class="history">
          {history_markup}
        </div>
      </section>
    </main>
  </body>
</html>
""".strip()


def _render_history(
    versions: list[PromptVersion],
    active_version_id: str | None,
    *,
    restore_action: str,
) -> str:
    if not versions:
        return '<p class="empty">No saved prompt versions yet. The app is currently using the built-in default prompt.</p>'

    blocks = []
    for version in versions:
        active_badge = '<span class="badge">Active</span>' if version.id == active_version_id else ""
        restore_form = (
            ""
            if version.id == active_version_id
            else (
                f'<form method="post" action="{html.escape(restore_action)}" class="inline">'
                f'<input type="hidden" name="version_id" value="{html.escape(version.id)}" />'
                '<button type="submit">Restore This Version</button>'
                "</form>"
            )
        )
        source_markup = (
            f"<span>source={html.escape(version.source_version_id)}</span>"
            if version.source_version_id
            else ""
        )
        blocks.append(
            f"""
<article class="history-card{' active' if version.id == active_version_id else ''}">
  <div class="meta">
    {active_badge}
    <span>id={html.escape(version.id)}</span>
    <span>action={html.escape(version.action)}</span>
    <span>saved_at={html.escape(version.created_at)}</span>
    <span>saved_by={html.escape(version.updated_by)}</span>
    {source_markup}
  </div>
  <pre>{html.escape(version.prompt)}</pre>
  <pre>{html.escape(version.opening_message)}</pre>
  {restore_form}
</article>
""".strip()
        )

    return "\n".join(blocks)
