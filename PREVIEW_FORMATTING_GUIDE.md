# Preview Formatting Implementation Guide

## The Problem

The AI generates **plain text paragraphs**, but your CSS expects **HTML structure** (h1, h2, p, ul, li tags). Result: walls of unformatted text.

---

## Solution: Update AI Prompt to Output HTML

### File: `app/api/opportunity_generate.py`

**Location:** Lines 234-242 (the REQUIREMENTS section of the prompt)

### Current Code:
```python
REQUIREMENTS:
1. Each response section must be 2-4 substantive paragraphs
2. Use specific details from the company profile (names, experience, certifications)
3. Match the RFP's tone and address stated requirements
4. Include concrete examples of relevant past projects
5. Submission checklist must include ALL narrative/form items required for submission
6. Use the EXACT section names as JSON keys (preserve spaces and capitalization)
7. If USER CONTEXT is provided for a section, incorporate that specific information prominently
```

### Replace With:
```python
REQUIREMENTS:
1. OUTPUT FORMAT: Each response section must be HTML-formatted for professional display:
   - Use <h2>Section Title</h2> for main headings
   - Use <h3>Subsection</h3> for sub-points
   - Wrap paragraphs in <p>...</p> tags
   - Use <ul><li>...</li></ul> for bullet lists
   - Use <strong>Company Name</strong> for emphasis on key terms
   - Use <em>...</em> for certifications and titles

2. STRUCTURE: Each section should include:
   - Opening paragraph introducing the topic
   - 2-3 supporting paragraphs with specific details
   - Bullet list of key qualifications or deliverables where appropriate
   - Closing paragraph with commitment statement

3. CONTENT:
   - Use specific details from the company profile (names, experience, certifications)
   - Match the RFP's tone and address stated requirements
   - Include concrete examples of relevant past projects
   - Reference specific certifications, years of experience, team members

4. Submission checklist must include ALL narrative/form items required for submission
5. Use the EXACT section names as JSON keys (preserve spaces and capitalization)
6. If USER CONTEXT is provided for a section, incorporate that specific information prominently
```

---

## Example Output Comparison

### Before (Plain Text):
```
EasyRFP, LLC is fully insured to meet the stringent requirements outlined by the Mid-Ohio Regional Planning Commission (MORPC) and the associated program funders. We understand the importance of comprehensive insurance coverage in safeguarding our operations and ensuring the security of all stakeholders involved. To this end, we hold a current Ohio Bureau of Workers' Compensation Certificate of Premium Payment. This certification is a testament to our commitment to employee welfare, as it ensures that our workforce is adequately protected in the unfortunate event of a workplace injury.
```

### After (HTML Formatted):
```html
<h2>Insurance & Risk Management</h2>

<p><strong>EasyRFP, LLC</strong> is fully insured to meet the stringent requirements outlined by the <em>Mid-Ohio Regional Planning Commission (MORPC)</em> and associated program funders. We understand the critical importance of comprehensive insurance coverage in safeguarding operations and ensuring security for all stakeholders.</p>

<h3>Current Coverage</h3>
<ul>
  <li><strong>Workers' Compensation:</strong> Current Ohio Bureau of Workers' Compensation Certificate of Premium Payment</li>
  <li><strong>General Liability:</strong> $2M per occurrence, $4M aggregate</li>
  <li><strong>Professional Liability:</strong> $1M coverage through A.M. Best A-rated carrier</li>
</ul>

<p>Our proactive approach to insurance and risk management is a cornerstone of our operational strategy. We continuously assess and update our policies to align with evolving industry standards and project-specific requirements.</p>

<h3>Additional Protections</h3>
<p>We possess the capability to add MORPC and program funders as <strong>additional insureds</strong> on our policy, providing an extra layer of protection for all parties involved.</p>
```

---

## CSS Already in Place

Your `ai-studio.css` (lines 1155-1196) already has professional styling for:

| Element | Style |
|---------|-------|
| `.preview-content` | Times New Roman, 12pt, 1.6 line-height |
| `h1` | 18pt, bold, centered |
| `h2` | 14pt, bold, bottom border |
| `h3` | 12pt, bold |
| `p` | Justified text, 12px margin |
| `ul/ol` | 28px left padding |
| `li` | 4px bottom margin |

**No CSS changes needed** - just generate HTML content!

---

## Optional Enhancements

### A. Add More Professional Styling

Add these to `ai-studio.css` after line 1196:

```css
/* Professional document enhancements */
.ai-tools-page .preview-content strong {
  color: #0f172a;
}

.ai-tools-page .preview-content em {
  font-style: italic;
  color: #334155;
}

.ai-tools-page .preview-content blockquote {
  border-left: 3px solid #126a45;
  padding-left: 16px;
  margin: 16px 0;
  color: #475569;
  font-style: italic;
}

.ai-tools-page .preview-content table {
  width: 100%;
  border-collapse: collapse;
  margin: 16px 0;
  font-size: 11pt;
}

.ai-tools-page .preview-content th,
.ai-tools-page .preview-content td {
  border: 1px solid #e2e8f0;
  padding: 10px 12px;
  text-align: left;
}

.ai-tools-page .preview-content th {
  background: #f8fafb;
  font-weight: 600;
}

.ai-tools-page .preview-content hr {
  border: none;
  border-top: 1px solid #e2e8f0;
  margin: 24px 0;
}
```

### B. Page Header/Footer (Optional)

For truly professional output, add document headers:

```css
.ai-tools-page .preview-page::before {
  content: attr(data-company) " | " attr(data-rfp);
  display: block;
  font-size: 9pt;
  color: #94a3b8;
  text-align: right;
  margin-bottom: 24px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e2e8f0;
}
```

---

## Implementation Steps

1. **Update the AI prompt** in `opportunity_generate.py` (lines 234-242)
2. **Test generation** with an RFP to verify HTML output
3. **Optionally add CSS enhancements** for tables, blockquotes, etc.

---

## For the Refine Endpoint (Improve/Shorten/Expand)

When you implement the `/refine` endpoint, also update those prompts to preserve HTML:

```python
prompts = {
    "improve": """Improve the following RFP response. Make it more professional, clear, and compelling.
IMPORTANT: Preserve all HTML formatting (h2, h3, p, ul, li, strong, em tags).
Enhance the content quality while maintaining the document structure.
Return ONLY the improved HTML content, no explanations.""",

    "shorten": """Shorten this RFP response by 30-40% while keeping essential information.
IMPORTANT: Preserve all HTML formatting (h2, h3, p, ul, li, strong, em tags).
Remove redundancy but maintain document structure.
Return ONLY the shortened HTML content, no explanations.""",

    "expand": """Expand this RFP response by 30-50% with more detail and examples.
IMPORTANT: Preserve all HTML formatting (h2, h3, p, ul, li, strong, em tags).
Add supporting details while maintaining professional tone.
Return ONLY the expanded HTML content, no explanations.""",
}
```

---

## Summary

| Change | File | What to Do |
|--------|------|------------|
| **Required** | `opportunity_generate.py` | Update prompt to request HTML output |
| **Optional** | `ai-studio.css` | Add styling for tables, blockquotes, hr |
| **Future** | Refine endpoint | Ensure HTML preservation in improve/shorten/expand |

The CSS is ready - you just need the AI to generate HTML!
