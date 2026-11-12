/**
 * 极简 Markdown -> 安全 HTML(用于 AI 回答展示)。
 * 先整体转义,再识别: 标题、粗体、行内代码、无序/有序列表、表格、分隔线、段落、http(s) 链接。
 */
function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function inline(s) {
  let t = esc(s)
  t = t.replace(/`([^`]+)`/g, '<code class="md-code">$1</code>')
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a class="md-a" href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
  return t
}

function splitRow(line) {
  let s = line.trim()
  if (s.startsWith('|')) s = s.slice(1)
  if (s.endsWith('|')) s = s.slice(0, -1)
  return s.split('|').map((c) => c.trim())
}

export function renderMarkdown(src) {
  const lines = String(src || '').replace(/\r/g, '').split('\n')
  const out = []
  let i = 0
  let para = []
  const flushPara = () => {
    if (para.length) {
      out.push(`<p class="md-p">${para.map(inline).join('<br/>')}</p>`)
      para = []
    }
  }
  while (i < lines.length) {
    const line = lines[i]
    const trimmed = line.trim()
    if (!trimmed) { flushPara(); i++; continue }

    let m = trimmed.match(/^(#{1,4})\s+(.*)$/)
    if (m) {
      flushPara()
      const lv = Math.min(m[1].length + 1, 4)
      out.push(`<div class="md-h md-h${lv}">${inline(m[2])}</div>`)
      i++; continue
    }
    if (/^(-{3,}|\*{3,})$/.test(trimmed)) { flushPara(); out.push('<div class="md-hr"></div>'); i++; continue }

    // 表格: 表头行 + 分隔行
    if (trimmed.includes('|') && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(lines[i + 1])) {
      flushPara()
      const head = splitRow(trimmed)
      i += 2
      const rows = []
      while (i < lines.length && lines[i].trim().includes('|')) { rows.push(splitRow(lines[i])); i++ }
      let h = '<div class="md-table-wrap"><table class="md-table"><thead><tr>'
      head.forEach((c) => { h += `<th>${inline(c)}</th>` })
      h += '</tr></thead><tbody>'
      rows.forEach((r) => {
        h += '<tr>'
        head.forEach((_, k) => { h += `<td>${inline(r[k] || '')}</td>` })
        h += '</tr>'
      })
      h += '</tbody></table></div>'
      out.push(h)
      continue
    }

    if (/^[-*]\s+/.test(trimmed) || /^\d+[.)]\s+/.test(trimmed)) {
      flushPara()
      const ordered = /^\d+[.)]\s+/.test(trimmed)
      const tag = ordered ? 'ol' : 'ul'
      let h = `<${tag} class="md-list">`
      while (i < lines.length) {
        const t = lines[i].trim()
        const mm = ordered ? t.match(/^\d+[.)]\s+(.*)$/) : t.match(/^[-*]\s+(.*)$/)
        if (!mm) break
        h += `<li>${inline(mm[1])}</li>`
        i++
      }
      h += `</${tag}>`
      out.push(h)
      continue
    }
    para.push(trimmed)
    i++
  }
  flushPara()
  return out.join('')
}
