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
  <div class="success-modal" id="successModal">
    <div class="success-content">
      <div class="success-icon">✓</div>
      <h3>All sections ready!</h3>
      <p>Your responses look complete. Time to review and export.</p>
      <button class="primary-btn" type="button" id="successClose">Close</button>
    </div>
  </div>
  <div class="preview-panel" id="previewPanel">
    <div class="preview-header">
      <h3>Document Preview</h3>
      <button class="close-preview" id="closePreview" type="button">×</button>
    </div>
    <div class="preview-tabs">
      <button class="preview-tab active" data-tab="cover" type="button">Cover Letter</button>
      <button class="preview-tab" data-tab="soq" type="button">SOQ</button>
      <button class="preview-tab" data-tab="full" type="button">Full Package</button>
    </div>
    <div class="preview-content" id="previewContent"></div>
    <div class="preview-footer">
      <button class="ghost-btn" type="button" id="previewEdit">Edit</button>
      <button class="primary-btn" type="button" id="previewExport">Export PDF</button>
    </div>
  </div>
  <section class="wizard-progress">
    <div class="progress-track">
      <div class="progress-fill" id="progressFill" style="width: 0%;"></div>
    </div>
    <div class="progress-steps" id="progressSteps">
      <div class="step completed" data-step="1">
        <div class="step-icon">✓</div>
        <div class="step-label">Upload</div>
      </div>
      <div class="step completed" data-step="2">
        <div class="step-icon">✓</div>
        <div class="step-label">Extract</div>
      </div>
      <div class="step active" data-step="3">
        <div class="step-icon">3</div>
        <div class="step-label">Answer</div>
        <div class="step-detail" id="progressDetail">0 of 0</div>
      </div>
      <div class="step" data-step="4">
        <div class="step-icon">4</div>
        <div class="step-label">Review</div>
      </div>
      <div class="step" data-step="5">
        <div class="step-icon">5</div>
        <div class="step-label">Export</div>
      </div>
    </div>
  </section>
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
    <div class="split-panel">
      <aside class="question-sidebar">
        <div class="sidebar-header">
          <h3>Questions</h3>
          <span class="badge" id="questionBadge">0/0</span>
        </div>
        <div class="question-list" id="questionList"></div>
        <button class="add-question-btn" id="addQuestionBtn" type="button">
          <span class="icon">+</span>
          Add Question
        </button>
      </aside>
      <main class="editor-panel">
        <div class="editor-header">
          <div class="question-nav">
            <button class="nav-btn" id="prevQuestion" type="button">←</button>
            <span class="question-number" id="questionNumber">Question 0 of 0</span>
            <button class="nav-btn" id="nextQuestion" type="button">→</button>
          </div>
          <div class="editor-actions">
            <button class="action-btn" id="regenerateBtn" type="button">
              <span class="icon">↻</span> Regenerate
            </button>
            <button class="action-btn success" id="approveBtn" type="button">
              <span class="icon">✓</span> Approve
            </button>
          </div>
        </div>
        <div class="question-display">
          <h2 id="currentQuestion">Select a question</h2>
          <div class="question-meta" id="questionMeta"></div>
        </div>
        <div class="answer-editor">
          <div class="editor-toolbar">
            <button class="toolbar-btn" title="Bold" type="button"><b>B</b></button>
            <button class="toolbar-btn" title="Italic" type="button"><i>I</i></button>
            <button class="toolbar-btn" title="Bullet list" type="button">•</button>
            <span class="toolbar-divider"></span>
            <button class="toolbar-btn" title="Insert from library" type="button">📚</button>
            <button class="toolbar-btn" title="AI suggestions" type="button">✨</button>
          </div>
          <div class="rich-editor" contenteditable="true" id="answerEditor"></div>
          <div class="editor-footer">
            <div class="word-count">
              <span class="count" id="wordCount">0</span>
              <span>/</span>
              <span id="wordLimit">0</span>
              <span>words</span>
              <span class="compliance-badge success" id="complianceBadge">Draft</span>
            </div>
            <div class="confidence-score">
              <span class="label">AI Confidence:</span>
              <div class="confidence-bar">
                <div class="confidence-fill" id="confidenceFill" style="width: 0%;"></div>
              </div>
              <span class="value" id="confidenceValue">0%</span>
            </div>
          </div>
        </div>
        <div class="ai-suggestions" id="suggestions" style="display:none;">
          <div class="suggestion-header">
            <span class="icon">💡</span>
            <span>AI Suggestions</span>
          </div>
          <div class="suggestion-item">
            <p id="suggestionText">Add specific metrics or references to boost compliance.</p>
            <button class="apply-btn" id="applySuggestion" type="button">Apply</button>
          </div>
        </div>
      </main>
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
