from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.api._layout import page_shell
from app.auth.session import get_current_user_email

router = APIRouter(tags=["ai-tools"])
STATIC_VER = "20251209.2"


@router.get("/ai-tools", response_class=HTMLResponse)
async def ai_tools_page(request: Request):
    user_email = get_current_user_email(request)
    body = f"""
<link rel="stylesheet" href="/static/css/dashboard.css?v={STATIC_VER}">
<link rel="stylesheet" href="/static/css/ai_tools.css?v={STATIC_VER}">

<main class="page ai-tools-page">
  <div id="sessionPicker" class="session-picker" style="display:none;"></div>
  <div id="saveIndicator" class="save-indicator">Saved</div>
  <header class="ai-header">
    <div>
      <p class="eyebrow">AI Studio</p>
      <h1>RFP Assistant</h1>
      <p class="lede">Start by generating the summary and checklist from your tracked solicitation, then create documents and answers.</p>
    </div>
    <div class="header-actions">
      <span class="pill success">OpenAI</span>
    </div>
  </header>

  <section class="card">
    <div class="section-heading">
      <div>
        <p class="eyebrow">Snapshot</p>
        <h2>RFP summary &amp; requirements</h2>
      </div>
      <button id="regenSummary" class="ghost-btn" type="button">Generate summary/checklist</button>
    </div>
    <div class="field" style="margin-bottom:12px;">
      <label>Opportunity</label>
      <select id="genOpportunity" required>
        <option value="">Select a tracked solicitation</option>
      </select>
      <p class="hint">We'll pull your uploaded RFP instructions for this opportunity.</p>
      <button id="refreshUploads" class="ghost-btn" type="button" style="margin-top:6px;">Load uploads</button>
    </div>
    <div class="card inset">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Step 1</p>
          <h3>Upload RFP</h3>
          <p class="hint">Drop the RFP file for this opportunity. Extraction runs automatically.</p>
        </div>
        <div class="right-actions">
          <input type="file" id="rfpUploadInput" style="display:none;" />
          <button id="rfpUploadBtn" class="primary-btn" type="button">Upload RFP</button>
        </div>
      </div>
      <p class="hint">Latest upload is used to extract summary, questions, and instructions.</p>
    </div>
    <div class="card inset">
      <div class="section-heading">
        <div>
          <p class="eyebrow">RFP instructions</p>
          <h3>Select uploaded instruction docs</h3>
        </div>
      </div>
      <div id="uploadsList" class="kb-list"></div>
    </div>
    <div id="summaryCard" class="summary-card empty" style="margin-top:12px;">Select an opportunity to load extracted summary.</div>
    <div class="grid two-col">
      <div>
        <h4>Checklist</h4>
        <ul id="checklist" class="simple-list"></ul>
      </div>
      <div>
        <h4>Submission instructions</h4>
        <div id="instructionsBlock" class="instructions-block"></div>
      </div>
    </div>
  </section>

  <section class="card">
    <div class="section-heading">
      <div>
        <p class="eyebrow">Auto-generated docs</p>
        <h2>Cover letter, SOQ, reminders</h2>
      </div>
      <button id="generateDocs" class="primary-btn" type="button">Generate documents</button>
    </div>
    <div id="docsContainer" class="docs-container empty">Generate to see documents.</div>
  </section>

  <section class="card">
    <div class="section-heading">
      <div>
        <p class="eyebrow">Preview &amp; edit</p>
        <h2>Fine-tune before export</h2>
      </div>
      <div class="right-actions">
        <button id="exportWord" class="primary-btn" type="button">Export Word</button>
        <button id="exportPdf" class="ghost-btn" type="button">Export PDF</button>
      </div>
    </div>
    <div class="grid two-col">
      <div class="field">
        <label>Cover letter</label>
        <textarea id="coverEdit" rows="12" style="width:100%;"></textarea>
      </div>
      <div class="field">
        <label>Statement of Qualifications (editable)</label>
        <textarea id="soqEdit" rows="12" style="width:100%;"></textarea>
      </div>
    </div>
  </section>

  <section class="card">
    <div class="section-heading">
      <div>
        <p class="eyebrow">Draft answers</p>
        <h2>Per-question content</h2>
      </div>
      <div class="right-actions">
        <div id="presenceBar" class="pill" style="display:none;">Live: <span id="presenceList">0</span></div>
        <button id="resultsClear" class="ghost-btn" type="button">Clear</button>
      </div>
    </div>
    <div class="card inset">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Step 3</p>
          <h3>Auto-detect questions</h3>
          <p class="hint">Detect questions from the uploaded RFP. You can edit or add more.</p>
        </div>
        <button id="detectQuestions" class="ghost-btn" type="button">Detect questions</button>
      </div>
    </div>
    <form id="genForm" class="stack">
      <div class="grid two-col">
        <div class="field">
          <label>Custom instructions</label>
          <input id="genInstructions" type="text" placeholder="Emphasize local presence and 24/7 response">
        </div>
      </div>
      <div class="card inset">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Sections</p>
            <h3>Add RFP questions</h3>
          </div>
          <button id="addSection" class="ghost-btn" type="button">Add section</button>
        </div>
        <div id="sectionsList" class="sections-list"></div>
        <div class="grid three-col" id="newSectionForm">
          <input id="secQuestion" type="text" placeholder="Question text">
          <input id="secMaxWords" type="number" min="0" placeholder="Max words (optional)">
          <label class="checkbox">
            <input id="secRequired" type="checkbox" checked>
            <span>Required</span>
          </label>
        </div>
      </div>
      <button class="primary-btn" type="submit">Generate with OpenAI</button>
    </form>
    <div id="results" class="results"></div>
    <div class="card inset">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Comments</p>
          <h3>Inline review</h3>
          <p class="hint">Comments sync live for all collaborators.</p>
        </div>
      </div>
      <div id="commentsList" class="comments-list"></div>
      <div class="grid two-col">
        <input id="commentText" type="text" placeholder="Add a comment about a section...">
        <button id="commentSend" class="ghost-btn" type="button">Send</button>
      </div>
    </div>
  </section>
</main>

<script>
  window.AI_TOOLS_CONFIG = {{ "user_email": "{user_email or ''}" }};
</script>
<script src="/static/js/ai_tools.js?v={STATIC_VER}"></script>
    """
    return HTMLResponse(page_shell(body, title="AI Studio", user_email=user_email))
