from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.api._layout import page_shell
from app.auth.session import get_current_user_email

router = APIRouter(tags=["ai-tools"])
STATIC_VER = "20251210.2"


@router.get("/ai-tools", response_class=HTMLResponse)
async def ai_tools_page(request: Request):
    user_email = get_current_user_email(request)
    body = f"""
<link rel="stylesheet" href="/static/css/ai-studio.css?v={STATIC_VER}">

<main class="ai-tools-page">
  <div class="wizard-container">
    <div class="wizard-header">
      <div style="display:flex;align-items:center;gap:14px;">
        <div class="wizard-icon">AI</div>
        <div>
          <h1 class="wizard-title">AI Proposal Studio</h1>
          <p class="wizard-subtitle">Upload, extract, draft, and export without leaving this flow.</p>
        </div>
      </div>
      <div class="wizard-actions">
        <button class="btn-secondary" type="button" id="resumeLatest">Load last session</button>
        <button class="btn-secondary" type="button" id="manualSave">Save now</button>
      </div>
    </div>

    <div class="progress-bar">
      <div class="progress-fill" id="progressFill" style="width:0%;"></div>
    </div>
    <div class="progress-label">
      <span id="progressText">Step 1 of 4</span>
      <span id="progressPercent">0% complete</span>
    </div>

    <div id="statusMessage" class="state-card hidden"></div>

    <div id="step1" class="wizard-step active">
      <div class="step-header">
        <div class="step-number">1</div>
        <div class="step-info">
          <h2>Select Opportunity &amp; Upload RFP</h2>
          <p>Choose a tracked solicitation and upload the RFP document</p>
        </div>
      </div>
      <div class="step-content">
        <div class="form-group">
          <label class="form-label" for="genOpportunity">Opportunity</label>
          <div class="select-wrapper">
            <select id="genOpportunity" class="form-select">
              <option value="">Select a tracked solicitation...</option>
            </select>
            <span class="select-arrow">&#9662;</span>
          </div>
        </div>
        <div class="document-switcher">
          <div class="doc-tabs" role="tablist">
            <button class="doc-tab active" type="button" data-tab="existing">Use Existing Document</button>
            <button class="doc-tab" type="button" data-tab="upload">Upload New Document</button>
          </div>
          <div class="doc-pane active" id="existingDocPane">
            <p class="doc-hint">Select any previously uploaded RFP or addendum for this opportunity.</p>
            <div id="existingDocsList" class="doc-list">
              <div class="doc-empty">Pick an opportunity to load your documents.</div>
            </div>
          </div>
          <div class="doc-pane" id="uploadDocPane">
            <p class="doc-hint">Upload a new file for this opportunity.</p>
            <div id="uploadArea" class="upload-area">
              <div class="upload-icon">&#128196;</div>
              <p class="upload-text">Drop your RFP here or click to browse</p>
              <p class="upload-hint">PDF, DOCX, or TXT up to 25MB</p>
              <input type="file" id="rfpUploadInput" hidden accept=".pdf,.docx,.doc,.txt" />
            </div>
            <div id="uploadedFile" class="uploaded-file hidden">
              <div class="file-icon">&#128196;</div>
              <div class="file-details">
                <span id="fileName" class="file-name"></span>
                <span id="fileSize" class="file-size"></span>
              </div>
              <button id="removeFile" class="file-remove" type="button" title="Remove file">&times;</button>
            </div>
          </div>
        </div>
      </div>
      <div class="step-actions">
        <button id="step1Next" class="btn-primary" type="button" disabled>
          Continue to Extraction &rarr;
        </button>
      </div>
    </div>

    <div id="step2" class="wizard-step">
      <div class="step-header">
        <div class="step-number">2</div>
        <div class="step-info">
          <h2>Extract RFP Information</h2>
          <p>AI will analyze your document and extract key details</p>
        </div>
      </div>
      <div class="step-content">
        <div class="extract-prompt">
          <p>We'll extract the following from your RFP:</p>
          <ul class="extract-list">
            <li>&#10003; Summary &amp; scope of work</li>
            <li>&#10003; Submission requirements</li>
            <li>&#10003; Required documents checklist</li>
            <li>&#10003; Key dates &amp; deadlines</li>
            <li>&#10003; Evaluation criteria</li>
            <li>&#10003; Contact information</li>
          </ul>
        </div>
        <button id="extractBtn" class="btn-extract" type="button" disabled>
          &#10024; Extract RFP Details
        </button>
        <div id="extractStatus" class="state-card hidden"></div>
        <div id="extractResults" class="extract-results hidden">
          <div class="result-columns">
            <div class="result-section">
              <h3>Summary</h3>
              <p id="summaryText"></p>
            </div>
            <div class="result-section">
              <h3>Checklist</h3>
              <ul id="checklistItems"></ul>
            </div>
          </div>
          <div class="result-section">
            <h3>Key Dates</h3>
            <div id="keyDates"></div>
          </div>
        </div>
      </div>
      <div class="step-actions">
        <button id="step2Back" class="btn-secondary" type="button">&larr; Back</button>
        <button id="step2Next" class="btn-primary" type="button" disabled>
          Continue to Generate &rarr;
        </button>
      </div>
    </div>

    <div id="step3" class="wizard-step">
      <div class="step-header">
        <div class="step-number">3</div>
        <div class="step-info">
          <h2>Generate &amp; Edit Response</h2>
          <p>AI will draft your cover letter and responses</p>
        </div>
      </div>
      <div class="step-content">
        <div id="generateOptions" class="generate-options">
          <!-- Dynamically populated from extracted narrative_sections -->
          <div class="loading-placeholder">Loading sections from extraction...</div>
        </div>
        <div class="custom-instructions form-group">
          <label class="form-label">Custom Instructions (optional)</label>
          <input id="customInstructions" class="form-input" placeholder="e.g., Emphasize our local presence and 24/7 support">
        </div>
        <button id="generateBtn" class="btn-generate" type="button" disabled>
          &#10024; Generate with AI
        </button>
        <div id="generateError" class="state-card error hidden"></div>

        <div id="documentEditor" class="document-editor hidden">
          <div class="editor-tabs">
            <!-- Tabs will be dynamically generated by JavaScript -->
            <div class="editor-tab-actions">
              <button class="tab-action" type="button" title="Fullscreen">&#9939;</button>
            </div>
          </div>
          <div class="editor-toolbar">
            <div class="toolbar-group">
              <button class="toolbar-btn" type="button" data-format="bold"><b>B</b></button>
              <button class="toolbar-btn" type="button" data-format="italic"><i>I</i></button>
              <button class="toolbar-btn" type="button" data-format="underline"><u>U</u></button>
            </div>
            <span class="toolbar-divider"></span>
            <div class="toolbar-group">
              <button class="toolbar-btn" type="button" data-format="h1">H1</button>
              <button class="toolbar-btn" type="button" data-format="h2">H2</button>
              <button class="toolbar-btn" type="button" data-format="h3">H3</button>
            </div>
            <span class="toolbar-divider"></span>
            <div class="toolbar-group">
              <button class="toolbar-btn" type="button" data-format="ul">&bull;</button>
              <button class="toolbar-btn" type="button" data-format="ol">1.</button>
            </div>
            <div class="toolbar-spacer"></div>
            <div class="badge success">Autosave ready</div>
          </div>
          <div class="editor-split">
            <div class="editor-pane">
              <div class="pane-header">EDIT</div>
              <div id="editableContent" class="editable-content" contenteditable="true"></div>
            </div>
            <div class="preview-pane">
              <div class="pane-header">PREVIEW</div>
              <div class="document-preview">
                <div class="preview-page">
                  <div id="previewContent" class="preview-content"></div>
                </div>
              </div>
            </div>
          </div>
          <div class="editor-footer">
            <div class="doc-status-bar">
              <span class="status-dot"></span>
              <span id="wordCount">0 words</span>
            </div>
            <div class="ai-actions">
              <button id="improveBtn" class="ai-action-btn" type="button">&#10024; Improve</button>
              <button id="shortenBtn" class="ai-action-btn" type="button">&#128201; Shorten</button>
              <button id="expandBtn" class="ai-action-btn" type="button">&#128200; Expand</button>
              <button class="ai-action-btn" type="button" id="manualSaveInline">Save</button>
            </div>
          </div>
        </div>
      </div>
      <div class="step-actions">
        <button class="btn-secondary" type="button" id="step3Back">&larr; Back</button>
        <button class="btn-primary" type="button" id="step3Next" disabled>
          Continue to Review &rarr;
        </button>
      </div>
    </div>

    <div id="step4" class="wizard-step">
      <div class="step-header">
        <div class="step-number">4</div>
        <div class="step-info">
          <h2>Review &amp; Export</h2>
          <p>Final review before downloading your response package</p>
        </div>
      </div>
      <div class="step-content">
        <div class="review-summary">
          <div class="review-item">
            <span>&#10003;</span>
            <div><strong>Opportunity</strong><span id="reviewOpportunity">&mdash;</span></div>
          </div>
          <div class="review-item">
            <span>&#10003;</span>
            <div><strong>Cover Letter</strong><span>Generated and edited</span></div>
          </div>
          <div class="review-item">
            <span>&#10003;</span>
            <div><strong>Statement of Qualifications</strong><span>Generated and edited</span></div>
          </div>
        </div>
        <div class="export-section">
          <h3>Download Your Package</h3>
          <p>Choose your preferred format</p>
          <div class="export-buttons">
            <button id="exportWord" class="btn-export" type="button">
              &#128196; <div><strong>Word Document</strong><span>.docx format</span></div>
            </button>
            <button id="exportPdf" class="btn-export" type="button">
              &#128213; <div><strong>PDF Document</strong><span>.pdf format</span></div>
            </button>
          </div>
        </div>
        <div id="completionMessage" class="completion-message hidden">
          <div class="completion-icon">&#10003;</div>
          <h3>Response Package Complete!</h3>
          <p>Your documents are ready for submission.</p>
          <button id="startNew" class="btn-primary">Start New Response</button>
        </div>
      </div>
      <div class="step-actions">
        <button class="btn-secondary" type="button" id="step4Back">&larr; Back to Edit</button>
      </div>
    </div>
  </div>
  <div id="saveIndicator" class="save-indicator hidden">Saved</div>
</main>

<script src="/static/js/ai-studio.js?v={STATIC_VER}"></script>
    """
    return HTMLResponse(page_shell(body, title="AI Studio", user_email=user_email))
