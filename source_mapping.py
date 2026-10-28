"""Conservative mapping for literal name macros and automatically numbered captions."""
import re

_CITE_SOURCE = re.compile(r'~?\\cite(?:\[[^\]]*\])*\{[^{}]+\}')
_CITE_GROUP = r'\[\d+(?:\s*[-–]\s*\d+)?(?:\s*,\s*\d+(?:\s*[-–]\s*\d+)?)*\]'
_CITE_DISPLAY = re.compile(_CITE_GROUP + r'(?:\s*,\s*' + _CITE_GROUP + r')*')
_CITE_MARK = '\ue000'


def _project_citations(text):
    return _CITE_DISPLAY.sub(_CITE_MARK, text)


def structured_matches(source, quote, revision, normalize, active_files=None):
    files = [(p, p.read_text(encoding='utf-8')) for p in (active_files or source.rglob('*.tex'))]
    definitions = {}
    for _, raw in files:
        preamble = raw.split(r'\begin{document}')[0]
        preamble = re.sub(r'(?<!\\)%[^\n]*', '', preamble)
        for m in re.finditer(r'\\(?:newcommand|renewcommand|providecommand)\s*\{(\\[A-Za-z]+)\}\s*\{([^{}$%#]+)\}', preamble):
            value = re.fullmatch(r'([^{}\\$%#]+?)(?:\\xspace)?', m[2])
            if value: definitions.setdefault(m[1], []).append((value[1], m[2].endswith(r'\xspace')))
    aliases = {k: v[0][0] for k, v in definitions.items() if len(v) == 1}
    spaced_aliases = {k for k, v in definitions.items() if len(v) == 1 and v[0][1]}
    caption_prefix = re.match(r'^((?:Figure|Fig\.|Table)\s+\d+[A-Za-z]?\s*[:.]\s*)', quote)
    found = []
    for path, raw in files:
        visible = re.sub(r'(?<!\\)%[^\n]*', lambda m: ' ' * len(m[0]), raw)
        # Only simple caption arguments are eligible; nested formatting stays protected.
        captions = [(m.start(1), m.end(1)) for m in re.finditer(r'\\caption\s*\{([^{}]*)\}', visible)]
        projected = []; starts = []; ends = []
        i = 0
        while i < len(visible):
            citation = _CITE_SOURCE.match(visible, i) if visible[i] in '~\\' else None
            if citation:
                if visible[i] == '~':
                    projected.append(' '); starts.append(i); ends.append(i+1); i += 1
                projected.append(_CITE_MARK); starts.append(i); ends.append(citation.end())
                i = citation.end()
                continue
            command = re.match(r'\\[A-Za-z]+', visible[i:]) if visible[i] == '\\' else None
            if command and command[0] in aliases:
                end = i + len(command[0]); value = aliases[command[0]]
                grouped = visible[end:end+2] == '{}'
                if grouped: end += 2
                for c in value: projected.append(c); starts.append(i); ends.append(end)
                i = end
                if visible[i:i+2] == '\\ ':  # Explicit space after a control word.
                    projected.append(' '); starts.append(i); ends.append(i+2); i += 2
                elif not grouped and i < len(visible) and visible[i].isspace():
                    space_start=i
                    while i < len(visible) and visible[i].isspace(): i += 1
                    if command[0] in spaced_aliases:
                        projected.append(' '); starts.append(space_start); ends.append(i)
                continue
            projected.append(visible[i]); starts.append(i); ends.append(i+1); i += 1
        text = ''.join(projected)
        normalized, offsets = normalize(text)
        variants = [(quote, '')]
        if caption_prefix: variants.append((quote[caption_prefix.end():], caption_prefix[0]))
        for target, label in variants:
            needle, _ = normalize(_project_citations(target.strip()))
            if not needle: continue
            pos = 0
            while True:
                at = normalized.find(needle, pos)
                if at < 0: break
                pos = at + 1
                if at and normalized[at-1].isalnum() and needle[0].isalnum(): continue
                stop = at+len(needle)
                if stop < len(normalized) and normalized[stop].isalnum() and needle[-1].isalnum(): continue
                a, b = offsets[at], offsets[stop-1]+1
                start, end = starts[a], ends[b-1]
                # Reject selecting part of an expanded macro.
                if a and starts[a-1] == start or b < len(starts) and ends[b] == end: continue
                if any(c in text[a:b] for c in '\\{}$%'): continue
                caption = next(((lo, hi) for lo, hi in captions if lo <= start and end <= hi), None)
                if label and not caption: continue
                prefix = visible[:start]
                document_start = prefix.find(r'\begin{document}')
                if document_start < 0:
                    # ACM stores the abstract before begin{document}.
                    abstract_start = prefix.rfind(r'\begin{abstract}')
                    if abstract_start < 0 or r'\end{abstract}' in prefix[abstract_start:]: continue
                    prefix = prefix[abstract_start:]
                else:
                    prefix = prefix[document_start+len(r'\begin{document}'):]
                if not caption:
                    if prefix.count('{') != prefix.count('}') or len(re.findall(r'(?<!\\)\$', prefix)) % 2: continue
                    stack = []
                    for env in re.finditer(r'\\(begin|end)\{([^}]+)\}', prefix):
                        if env[1] == 'begin': stack.append(env[2])
                        elif stack and stack[-1] == env[2]: stack.pop()
                    if any(e not in ('abstract', 'quote', 'quotation', 'itemize', 'enumerate') for e in stack): continue
                    math_open = False
                    for token in re.finditer(r'\\(\\|[\[\]()])', prefix):
                        if token[1] in ('[', '('): math_open = True
                        elif token[1] in (']', ')'): math_open = False
                    if math_open: continue
                before = raw[start:end]
                used = {k: v for k, v in aliases.items() if re.search(re.escape(k)+r'(?![A-Za-z])', before)}
                source_citations = _CITE_SOURCE.findall(before)
                display_citations = _CITE_DISPLAY.findall(target)
                if len(source_citations) != len(display_citations): continue
                found.append(dict(file=path.relative_to(source).as_posix(), start=start, end=end,
                                  raw_before=before, line=raw[:start].count('\n')+1, revision=revision,
                                  match_mode='literal-macros-caption', aliases=used, caption_prefix=label,
                                  citations=list(zip(display_citations, source_citations))))
    return list({(m['file'], m['start'], m['end']): m for m in found}.values())


def replacement_source(text, match, escape):
    prefix = match.get('caption_prefix', '')
    if prefix:
        label = re.match(r'^((?:Figure|Fig\.|Table)\s+\d+[A-Za-z]?\s*[:.]\s*)', text)
        if label:
            if label[0].strip() != prefix.strip(): raise ValueError('建议改变了图表编号，请先修正建议。')
            text = text[label.end():]
    # Restore only known literal aliases that occurred in the selected source.
    aliases = match.get('aliases', {})
    by_value = {}
    for command, value in aliases.items(): by_value.setdefault(value, []).append(command)
    values = [v for v, commands in by_value.items() if len(commands) == 1]
    pattern = re.compile(r'(?<!\w)('+'|'.join(re.escape(v) for v in sorted(values,key=len,reverse=True))+r')(?!\w)') if values else None
    def render(segment):
        if not pattern:return ''.join(escape.get(c,c) for c in segment)
        out=[];pos=0
        for m in pattern.finditer(segment):
            out.append(''.join(escape.get(c,c) for c in segment[pos:m.start()]))
            out.append(by_value[m[0]][0]+'{}');pos=m.end()
        out.append(''.join(escape.get(c,c) for c in segment[pos:]))
        return ''.join(out)
    citations=match.get('citations',[])
    displays=list(_CITE_DISPLAY.finditer(text))
    if len(displays)!=len(citations):raise ValueError('改写建议改变了引用数量，请先修正建议。')
    out=[];pos=0
    for display,(original,source) in zip(displays,citations):
        numbers=lambda value: sorted(re.findall(r'\d+',value))
        if numbers(display[0])!=numbers(original):raise ValueError('改写建议改变了引用编号，请先修正建议。')
        segment=text[pos:display.start()]
        if source.startswith('~'):segment=segment.rstrip(' ')
        out.extend((render(segment),source));pos=display.end()
    out.append(render(text[pos:]))
    return ''.join(out)
