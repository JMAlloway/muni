document.addEventListener('DOMContentLoaded', function() {
  let currentStep = 1;
  let fileUploaded = false;
  let opportunitySelected = false;
  let extracted = false;
  let generated = false;
  let currentDoc = 'cover';

  const documents = {
    cover: '',
    responses: ''
  };

  const steps = {
    1: document.getElementById('step1'),
    2: document.getElementById('step2'),
    3: document.getElementById('step3'),
    4: document.getElementById('step4')
  };

  const progressFill = document.getElementById('progressFill');
  const progressText = document.getElementById('progressText');
  const progressPercent = document.getElementById('progressPercent');
  const saveIndicator = document.getElementById('saveIndicator');

  const genOpportunity = document.getElementById('genOpportunity');
  const uploadArea = document.getElementById('uploadArea');
  const rfpUploadInput = document.getElementById('rfpUploadInput');
  const uploadedFile = document.getElementById('uploadedFile');
  const fileName = document.getElementById('fileName');
  const fileSize = document.getElementById('fileSize');
  const removeFile = document.getElementById('removeFile');
  const step1Next = document.getElementById('step1Next');

  const extractBtn = document.getElementById('extractBtn');
  const extractResults = document.getElementById('extractResults');
  const step2Next = document.getElementById('step2Next');
  const step2Back = document.getElementById('step2Back');

  const generateBtn = document.getElementById('generateBtn');
  const documentEditor = document.getElementById('documentEditor');
  const editableContent = document.getElementById('editableContent');
  const previewContent = document.getElementById('previewContent');
  const wordCount = document.getElementById('wordCount');
  const step3Next = document.getElementById('step3Next');
  const step3Back = document.getElementById('step3Back');

  const step4Back = document.getElementById('step4Back');
  const exportWord = document.getElementById('exportWord');
  const exportPdf = document.getElementById('exportPdf');
  const completionMessage = document.getElementById('completionMessage');
  const startNew = document.getElementById('startNew');

  function updateProgress() {
    const percent = ((currentStep - 1) / 3) * 100;
    progressFill.style.width = percent + '%';
    progressText.textContent = `Step ${currentStep} of 4`;
    progressPercent.textContent = Math.round(percent) + '% complete';
  }

  function goToStep(step) {
    for (let i = 1; i <= 4; i++) {
      steps[i].classList.remove('active', 'completed');
      if (i < step) {
        steps[i].classList.add('completed');
      } else if (i === step) {
        steps[i].classList.add('active');
      }
    }
    currentStep = step;
    updateProgress();
  }

  function checkStep1() {
    step1Next.disabled = !(opportunitySelected && fileUploaded);
  }

  function showSave() {
    saveIndicator.classList.remove('hidden');
    setTimeout(() => saveIndicator.classList.add('hidden'), 2000);
  }

  function updateWordCount() {
    const text = editableContent.innerText || '';
    const words = text.trim().split(/\s+/).filter(w => w.length > 0).length;
    wordCount.textContent = words + ' word' + (words !== 1 ? 's' : '');
  }

  function updatePreview() {
    previewContent.innerHTML = editableContent.innerHTML;
  }

  function switchDocument(docType) {
    documents[currentDoc] = editableContent.innerHTML;
    currentDoc = docType;
    editableContent.innerHTML = documents[docType];
    updatePreview();
    updateWordCount();

    document.querySelectorAll('.editor-tab').forEach(tab => {
      tab.classList.toggle('active', tab.dataset.doc === docType);
    });
  }

  genOpportunity.addEventListener('change', function() {
    opportunitySelected = this.value !== '';
    checkStep1();
    if (opportunitySelected) showSave();
  });

  uploadArea.addEventListener('click', () => rfpUploadInput.click());

  uploadArea.addEventListener('dragover', function(e) {
    e.preventDefault();
    uploadArea.classList.add('drag-over');
  });

  uploadArea.addEventListener('dragleave', function() {
    uploadArea.classList.remove('drag-over');
  });

  uploadArea.addEventListener('drop', function(e) {
    e.preventDefault();
    uploadArea.classList.remove('drag-over');
    if (e.dataTransfer.files.length) {
      handleFile(e.dataTransfer.files[0]);
    }
  });

  rfpUploadInput.addEventListener('change', function(e) {
    if (e.target.files.length) {
      handleFile(e.target.files[0]);
    }
  });

  function handleFile(file) {
    fileName.textContent = file.name;
    fileSize.textContent = (file.size / (1024 * 1024)).toFixed(2) + ' MB';
    uploadedFile.classList.remove('hidden');
    uploadArea.style.display = 'none';
    fileUploaded = true;
    checkStep1();
    showSave();
  }

  removeFile.addEventListener('click', function() {
    uploadedFile.classList.add('hidden');
    uploadArea.style.display = 'block';
    rfpUploadInput.value = '';
    fileUploaded = false;
    checkStep1();
  });

  step1Next.addEventListener('click', function() {
    goToStep(2);
  });

  step2Back.addEventListener('click', function() {
    goToStep(1);
  });

  extractBtn.addEventListener('click', function() {
    extractBtn.innerHTML = `
      <svg class="spin" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
      </svg>
      Analyzing RFP...
    `;
    extractBtn.disabled = true;

    setTimeout(function() {
      document.getElementById('summaryText').textContent = 
        'The City of Columbus Parks & Recreation Department is seeking qualified contractors for comprehensive landscape maintenance services across 47 municipal parks. The contract period is 3 years with two optional 1-year extensions. Services include mowing, trimming, seasonal planting, irrigation maintenance, and snow removal.';

      document.getElementById('checklistItems').innerHTML = `
        <li>Cover Letter (max 2 pages)</li>
        <li>Statement of Qualifications</li>
        <li>3 Project References (within 5 years)</li>
        <li>Proof of Insurance ($2M minimum)</li>
        <li>Equipment List</li>
        <li>Pricing Schedule</li>
      `;

      document.getElementById('keyDates').innerHTML = `
        <p style="margin: 0 0 8px;"><strong>Deadline:</strong> January 15, 2025 at 2:00 PM</p>
        <p style="margin: 0 0 8px;"><strong>Questions due:</strong> January 5, 2025</p>
        <p style="margin: 0;"><strong>Award date:</strong> February 1, 2025</p>
      `;

      extractResults.classList.remove('hidden');
      extractBtn.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20 6L9 17l-5-5"/>
        </svg>
        Extraction Complete
      `;
      extractBtn.style.background = '#10b981';
      extractBtn.style.boxShadow = '0 6px 24px rgba(16, 185, 129, 0.35)';
      
      extracted = true;
      step2Next.disabled = false;
      showSave();
    }, 2000);
  });

  step2Next.addEventListener('click', function() {
    goToStep(3);
  });

  step3Back.addEventListener('click', function() {
    goToStep(2);
  });

  document.querySelectorAll('.generate-option').forEach(option => {
    option.addEventListener('click', function() {
      this.classList.toggle('selected');
      this.querySelector('input').checked = this.classList.contains('selected');
    });
  });

  generateBtn.addEventListener('click', function() {
    generateBtn.innerHTML = `
      <svg class="spin" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
      </svg>
      Generating Response...
    `;
    generateBtn.disabled = true;

    setTimeout(function() {
      documents.cover = `<p><strong>[Your Company Letterhead]</strong></p>
<p>January 10, 2025</p>
<p>City of Columbus<br>Parks & Recreation Department<br>1111 E Broad St<br>Columbus, OH 43205</p>
<p><strong>RE: RFP 2025-PR-001 - Landscape Maintenance Services</strong></p>
<p>Dear Selection Committee,</p>
<p>We are pleased to submit our proposal for the Landscape Maintenance Services contract. With over 25 years of experience serving Central Ohio municipalities, we understand the unique requirements of maintaining public green spaces to the highest standards.</p>
<p>Our team has successfully managed similar contracts with Franklin County, Westerville, and Dublin, consistently exceeding performance metrics and earning recognition for our commitment to sustainability and community engagement.</p>
<p>We look forward to the opportunity to partner with the City of Columbus.</p>
<p>Respectfully,</p>
<p><strong>[Signature Block]</strong></p>`;

      documents.responses = `<h2>Question 1</h2>
<p><em>Describe your company's experience with municipal landscape maintenance contracts.</em></p>
<p>Our company has proudly served Central Ohio municipalities for over 25 years. Our portfolio includes ongoing contracts with Franklin County Parks (32 properties since 2019), the City of Dublin (municipal campus since 2017), and previously the City of Westerville (parks and trails, 2015-2022).</p>
<p>Throughout these engagements, we have consistently exceeded performance metrics, maintained 98% on-time service completion, and received commendations for our responsive communication.</p>
<h2>Question 2</h2>
<p><em>Outline your approach to sustainable landscape practices.</em></p>
<p>Environmental stewardship is central to our operations. We employ integrated pest management (IPM) protocols, use electric and hybrid equipment where possible, and have reduced fuel consumption by 35% through route optimization.</p>
<p>Our sustainability initiatives include:</p>
<ul>
<li>Native plant species recommendations</li>
<li>Water-efficient irrigation scheduling</li>
<li>Organic fertilizer programs</li>
<li>Pollinator habitat preservation</li>
</ul>`;

      currentDoc = 'cover';
      editableContent.innerHTML = documents.cover;
      updatePreview();
      updateWordCount();

      documentEditor.classList.remove('hidden');
      generateBtn.style.display = 'none';
      document.querySelector('.generate-options').style.display = 'none';
      document.querySelector('.custom-instructions').style.display = 'none';
      
      generated = true;
      step3Next.disabled = false;
      showSave();
    }, 2500);
  });

  document.querySelectorAll('.editor-tab').forEach(tab => {
    tab.addEventListener('click', function() {
      if (this.dataset.doc) {
        switchDocument(this.dataset.doc);
      }
    });
  });

  editableContent.addEventListener('input', function() {
    updatePreview();
    updateWordCount();
    documents[currentDoc] = editableContent.innerHTML;
  });

  document.querySelectorAll('.toolbar-btn').forEach(btn => {
    btn.addEventListener('click', function() {
      const format = this.dataset.format;
      if (!format) return;

      switch(format) {
        case 'bold':
          document.execCommand('bold', false, null);
          break;
        case 'italic':
          document.execCommand('italic', false, null);
          break;
        case 'underline':
          document.execCommand('underline', false, null);
          break;
        case 'h1':
          document.execCommand('formatBlock', false, 'h1');
          break;
        case 'h2':
          document.execCommand('formatBlock', false, 'h2');
          break;
        case 'h3':
          document.execCommand('formatBlock', false, 'h3');
          break;
        case 'ul':
          document.execCommand('insertUnorderedList', false, null);
          break;
        case 'ol':
          document.execCommand('insertOrderedList', false, null);
          break;
      }

      editableContent.focus();
      updatePreview();
      documents[currentDoc] = editableContent.innerHTML;
    });
  });

  const improveBtn = document.getElementById('improveBtn');
  const shortenBtn = document.getElementById('shortenBtn');
  const expandBtn = document.getElementById('expandBtn');

  function simulateAiAction(btn, action) {
    const originalText = btn.innerHTML;
    btn.innerHTML = `<svg class="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> Working...`;
    btn.disabled = true;

    setTimeout(() => {
      btn.innerHTML = originalText;
      btn.disabled = false;
      showSave();
    }, 1500);
  }

  if (improveBtn) improveBtn.addEventListener('click', () => simulateAiAction(improveBtn, 'improve'));
  if (shortenBtn) shortenBtn.addEventListener('click', () => simulateAiAction(shortenBtn, 'shorten'));
  if (expandBtn) expandBtn.addEventListener('click', () => simulateAiAction(expandBtn, 'expand'));

  step3Next.addEventListener('click', function() {
    documents[currentDoc] = editableContent.innerHTML;
    const selectedOpp = genOpportunity.options[genOpportunity.selectedIndex].text;
    document.getElementById('reviewOpportunity').textContent = selectedOpp;
    goToStep(4);
  });

  step4Back.addEventListener('click', function() {
    goToStep(3);
  });

  exportWord.addEventListener('click', function() {
    exportWord.innerHTML = `
      <svg class="spin" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
      </svg>
      <div><strong>Exporting...</strong></div>
    `;

    setTimeout(function() {
      exportWord.innerHTML = `
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2">
          <path d="M20 6L9 17l-5-5"/>
        </svg>
        <div><strong>Downloaded!</strong><span>.docx format</span></div>
      `;
      completionMessage.classList.remove('hidden');
      progressFill.style.width = '100%';
      progressPercent.textContent = '100% complete';
    }, 1500);
  });

  exportPdf.addEventListener('click', function() {
    exportPdf.innerHTML = `
      <svg class="spin" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
      </svg>
      <div><strong>Exporting...</strong></div>
    `;

    setTimeout(function() {
      exportPdf.innerHTML = `
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2">
          <path d="M20 6L9 17l-5-5"/>
        </svg>
        <div><strong>Downloaded!</strong><span>.pdf format</span></div>
      `;
      completionMessage.classList.remove('hidden');
      progressFill.style.width = '100%';
      progressPercent.textContent = '100% complete';
    }, 1500);
  });

  startNew.addEventListener('click', function() {
    location.reload();
  });

  goToStep(1);
});
