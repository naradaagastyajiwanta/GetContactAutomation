---
name: read-docx
description: >
  Extract and convert Word documents (.docx) to structured markdown.
  Preserves tables, headings, lists, and formatting.
  Output: docs/extracted/[filename].md — ready for brief-interpreter
  or qa-checklist-interpreter.
allowed-tools: Bash, Read, Write
---

# Read Word → Markdown

Converts any .docx file to structured markdown, preserving document structure.

## When to Use
- Brief files from PM in `.docx` format
- QA test cases in Word documents
- Any agent needs to read content from a Word file

## Process

### Step 1: Convert with Pandoc (preferred)

```bash
BASENAME=$(basename "INPUT_FILE" .docx)
mkdir -p docs/extracted

pandoc "INPUT_FILE" \
  --from=docx \
  --to=gfm \
  --wrap=none \
  --track-changes=all \
  -o "docs/extracted/${BASENAME}.md"

echo "Extracted to: docs/extracted/${BASENAME}.md"
cat "docs/extracted/${BASENAME}.md"
```

Pandoc preserves:
- Headings (h1-h6)
- Tables (as markdown tables)
- Bullet and numbered lists
- Bold, italic, strikethrough
- Track changes (if present)

### Step 2: Fallback — Python docx2txt

If pandoc is not available:
```bash
pip install python-docx 2>/dev/null || pip3 install python-docx 2>/dev/null

/usr/bin/python3 << 'PYEOF'
from docx import Document
import os

input_file = "INPUT_FILE"
basename = os.path.splitext(os.path.basename(input_file))[0]
output_file = f"docs/extracted/{basename}.md"

doc = Document(input_file)

with open(output_file, 'w') as out:
    out.write(f"# {basename}\n")
    out.write(f"Source: `{input_file}`\n\n---\n\n")

    for element in doc.element.body:
        tag = element.tag.split('}')[-1]

        if tag == 'p':
            para = None
            for p in doc.paragraphs:
                if p._element == element:
                    para = p
                    break
            if para:
                style = para.style.name if para.style else ""
                text = para.text.strip()
                if not text:
                    out.write("\n")
                elif "Heading 1" in style:
                    out.write(f"## {text}\n\n")
                elif "Heading 2" in style:
                    out.write(f"### {text}\n\n")
                elif "Heading 3" in style:
                    out.write(f"#### {text}\n\n")
                elif "List" in style:
                    out.write(f"- {text}\n")
                else:
                    out.write(f"{text}\n\n")

        elif tag == 'tbl':
            for table in doc.tables:
                if table._element == element:
                    rows = table.rows
                    if not rows:
                        continue
                    # Header
                    headers = [cell.text.strip() for cell in rows[0].cells]
                    out.write("| " + " | ".join(headers) + " |\n")
                    out.write("| " + " | ".join(["---"] * len(headers)) + " |\n")
                    # Data
                    for row in rows[1:]:
                        cells = [cell.text.strip().replace("|", "\\|") for cell in row.cells]
                        out.write("| " + " | ".join(cells) + " |\n")
                    out.write("\n")
                    break

print(f"Extracted to: {output_file}")
PYEOF
```

### Step 3: Last Resort — Raw XML Extraction

If neither pandoc nor python-docx available:
```bash
BASENAME=$(basename "INPUT_FILE" .docx)
mkdir -p docs/extracted

unzip -p "INPUT_FILE" word/document.xml | \
  sed 's/<\/w:p>/\n/g' | \
  sed 's/<[^>]*>//g' | \
  sed '/^$/d' \
  > "docs/extracted/${BASENAME}.md"

echo "⚠️ Raw extraction (no formatting). Install pandoc for better results."
```

### Step 4: Verify Output

```bash
OUTPUT_FILE="docs/extracted/[basename].md"
wc -l "$OUTPUT_FILE"
head -40 "$OUTPUT_FILE"
```

## Integration with Pipeline

When called from `brief-reader` or `qa-checklist-interpreter`:
1. Agent detects `.docx` extension
2. Calls this skill to convert → `docs/extracted/[name].md`
3. Agent reads the markdown output
4. Continues with its normal processing
