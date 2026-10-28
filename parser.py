"""Local, text-first PDF extraction. No model or network calls.

Reading order is inferred in unrotated page coordinates; UI anchors are
transformed to the rendered page's normalized coordinate system.
"""
import hashlib
import re
import statistics
from collections import Counter

import pymupdf as fitz
from math_layout import annotate_row, equation_regions, inline_math, merge_inline_rows, formula_clip_boxes

PARSER_VERSION = 'columns-1.4-tables'


def tidy_lines(lines):
    text = ''
    for line in lines:
        s = line['text'].strip()
        if not s:
            continue
        if text.endswith('-') and s[0].islower() and len(text) > 1 and text[-2].isalpha():
            text = text[:-1] + s
        else:
            text += (' ' if text else '') + s
    return re.sub(r'\s+', ' ', text).strip()


def normalized_rect(rect, page):
    r = fitz.Rect(rect) * page.rotation_matrix
    w, h = page.rect.width, page.rect.height
    return [round(max(0, min(1, v)), 6) for v in (r.x0 / w, r.y0 / h, r.x1 / w, r.y1 / h)]


def extract_lines(page):
    rows = []
    for bi, block in enumerate(page.get_text('dict', flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)['blocks']):
        if block.get('type') != 0:
            continue
        for li, line in enumerate(block.get('lines', [])):
            spans = [s for s in line['spans'] if s['text'].strip()]
            if not spans:
                continue
            txt = ''.join(s['text'] for s in line['spans']).strip()
            rows.append({'text': txt, 'bbox': list(line['bbox']), 'block': bi, 'line': li,
                         'size': statistics.median(s['size'] for s in spans),
                         'bold': any(s['flags'] & 16 for s in spans),
                         'dir': list(line.get('dir', [1, 0]))})
            annotate_row(rows[-1],line['spans'])
    return merge_inline_rows(rows)


def infer_gutter(lines, width):
    # Compare candidate gaps using normal-length lines, so headings and equation
    # labels cannot create a spurious second column.
    eligible = [l for l in lines if len(l['text']) >= 22 and l['bbox'][2] - l['bbox'][0] < width * .69]
    if len(eligible) < 8:
        return None, 0.0
    best = None
    for n in range(38, 63):
        x = width * n / 100
        left = [l for l in eligible if l['bbox'][2] <= x + 2]
        right = [l for l in eligible if l['bbox'][0] >= x - 2]
        if min(len(left), len(right)) < 4:
            continue
        crossing = len(eligible) - len(left) - len(right)
        balance = min(len(left), len(right)) / max(len(left), len(right))
        score = (len(left) + len(right) - 3 * crossing) / len(eligible) + .12 * balance
        # Require a real separation between typical left endings / right starts.
        edge_l = max(l['bbox'][2] for l in left)
        edge_r = min(l['bbox'][0] for l in right)
        if edge_r - edge_l < width * .008:
            continue
        if best is None or score > best[0]:
            best = (score, (edge_l + edge_r) / 2, crossing / len(eligible))
    if best is None or best[0] < .68 or best[2] > .22:
        return None, 0.0
    return best[1], min(.98, round(best[0] / 1.12, 2))


def visual_regions(page, rows):
    """Preserve figures and ruled tables as source crops, not invented prose.

    Table detection is deliberately restricted to repeated horizontal rules
    below a TABLE caption. Unruled tables remain text requiring manual review.
    """
    width = page.cropbox.width
    regions = []
    for image in page.get_image_info():
        r = fitz.Rect(image['bbox'])
        if r.width > width * .18 and r.height > 45:
            regions.append(('figure', list(r)))
    drawings = page.get_drawings()
    captions = [r for r in rows if re.match(r'^(?:Fig(?:ure)?\.?\s*\d|TABLE\s+[IVX\d]+)', r['text'], re.I)]
    try:
        for r in page.cluster_drawings(drawings=drawings):
            near_caption = any(0 <= c['bbox'][1] - r.y1 < 65 and c['text'].lower().startswith('fig') for c in captions)
            count = sum(1 for d in drawings if r.contains(d['rect']))
            if count >= 8 and r.width > width * .25 and r.height > 60 and near_caption:
                regions.append(('figure', list(r)))
    except (AttributeError, TypeError):
        pass
    groups = {}
    for d in drawings:
        for item in d['items']:
            if item[0] != 'l':
                continue
            a,b = item[1],item[2]
            x0,x1 = sorted((a.x,b.x))
            if abs(a.y-b.y) < 1 and x1-x0 > width * .2:
                key = (round(x0/5),round(x1/5))
                groups.setdefault(key,[]).append((x0,x1,a.y))
    for rules in groups.values():
        rules = sorted(rules,key=lambda r:r[2])
        runs, run = [], []
        for rule in rules:
            between_captions = run and any(
                c['text'].upper().startswith('TABLE')
                and run[-1][2] + 2 < c['bbox'][1]
                and c['bbox'][3] + 2 < rule[2]
                and rule[0] - 8 <= (c['bbox'][0] + c['bbox'][2]) / 2 <= rule[1] + 8
                for c in captions
            )
            if run and (rule[2]-run[-1][2] > 110 or between_captions):
                runs.append(run);run=[]
            run.append(rule)
        if run:
            runs.append(run)
        for run in runs:
            if len(run) < 3 or run[-1][2]-run[0][2] < 20:
                continue
            x0,x1,y0 = run[0]
            y1=run[-1][2]
            has_caption=any(c['text'].upper().startswith('TABLE') and 0<=y0-c['bbox'][3]<100 and x0-8<=sum(c['bbox'][::2])/2<=x1+8 for c in captions)
            if not has_caption:
                continue
            rect=fitz.Rect(x0-2,y0-2,x1+2,y1+2)
            if any((rect & fitz.Rect(r)).get_area() > rect.get_area()*.5 for _,r in regions):
                continue
            regions.append(('table',list(rect)))
    return regions


def classify(text, lines, body_size):
    size = statistics.median(l['size'] for l in lines)
    if re.match(r'^(fig(?:ure)?\.?\s*\d|table\s+[\divx]+)', text, re.I):
        return 'caption'
    if len(text) < 190 and (size > body_size * 1.18 or re.match(r'^(?:[IVX]+\.|\d+(?:\.\d+)*\.?)[ ]+[A-Z]', text)):
        return 'heading'
    if len(text) < 90 and (text.isupper() or (len(lines) <= 2 and all(l['bold'] for l in lines))):
        return 'heading'
    if re.match(r'^\[\d+\]', text):
        return 'reference'
    symbols = sum(c in '=∑∫≈≤≥∂√' for c in text)
    if symbols and len(text.split()) < 12 and len(text) < 180:
        return 'equation'
    return 'paragraph'


def order_blocks(blocks, gutter):
    if gutter is None:
        return sorted(blocks, key=lambda b: (b['source_bbox'][1], b['source_bbox'][0]))
    wide = sorted([b for b in blocks if b['column'] == 'wide'], key=lambda b: b['source_bbox'][1])
    remaining = [b for b in blocks if b['column'] != 'wide']
    result = []
    for barrier in wide:
        y = barrier['source_bbox'][1]
        before = [b for b in remaining if (b['source_bbox'][1] + b['source_bbox'][3]) / 2 < y]
        remaining = [b for b in remaining if b not in before]
        for col in ('left', 'right'):
            result.extend(sorted([b for b in before if b['column'] == col], key=lambda b: b['source_bbox'][1]))
        result.append(barrier)
    for col in ('left', 'right'):
        result.extend(sorted([b for b in remaining if b['column'] == col], key=lambda b: b['source_bbox'][1]))
    return result


def parse_pdf(path, progress=None):
    with fitz.open(path) as pdf:
        if pdf.needs_pass:
            raise ValueError('PDF 有密码保护，请先使用无密码副本。')
        if len(pdf) > 200:
            raise ValueError('验证版最多支持 200 页，请截取需要验证的章节。')
        all_lines = [extract_lines(p) for p in pdf]
        margins = Counter()
        for p, rows in zip(pdf, all_lines):
            height = p.cropbox.height
            seen = set()
            for row in rows:
                if row['bbox'][1] < height * .07 or row['bbox'][3] > height * .94:
                    s = re.sub(r'\d+', '#', row['text'])
                    seen.add(s)
            margins.update(seen)
        pages, fulltext, order = [], [], 0
        for pi, (page, rows) in enumerate(zip(pdf, all_lines)):
            if progress:
                progress(pi, len(pdf))
            width, height = page.cropbox.width, page.cropbox.height
            sizes = [r['size'] for r in rows for _ in range(min(len(r['text']), 100))]
            body_size = statistics.median(sizes) if sizes else 10
            regular, excluded = [], []
            for r in rows:
                margin = r['bbox'][1] < height * .07 or r['bbox'][3] > height * .94
                repeat = margins[re.sub(r'\d+', '#', r['text'])] >= max(2, len(pdf) * .5)
                page_no = bool(re.fullmatch(r'\s*(?:\d+|[ivx]+)\s*', r['text'], re.I))
                (excluded if margin and (repeat or page_no) else regular).append(r)
            regions = visual_regions(page, regular)
            outside=[r for r in regular if not any((fitz.Rect(r['bbox']) & fitz.Rect(box)).get_area()>=fitz.Rect(r['bbox']).get_area()*.7 for _,box in regions)]
            initial_gutter,_=infer_gutter(outside,width)
            regions.extend(equation_regions(outside,initial_gutter,width,body_size))
            region_text = {i: [] for i in range(len(regions))}
            prose = []
            for r in regular:
                box = fitz.Rect(r['bbox'])
                owner = next((i for i,(_,region) in enumerate(regions) if (box & fitz.Rect(region)).get_area() >= box.get_area()*.7), None)
                if owner is None:
                    prose.append(r)
                else:
                    region_text[owner].append(r)
            regular = prose
            gutter, score = infer_gutter(regular, width)
            # A full-width paragraph often ends with a short line in the left
            # half. Keep that last line with its original paragraph. Only split
            # actual mixed-column blocks whose lines start in both columns.
            wide_blocks = set()
            if gutter is not None:
                for bi in {r['block'] for r in regular}:
                    original = [r for r in regular if r['block'] == bi]
                    crosses = any(r['bbox'][0] < gutter - 3 and r['bbox'][2] > gutter + 3 for r in original)
                    starts_right = any(r['bbox'][0] >= gutter - 3 for r in original)
                    if crosses and not starts_right:
                        wide_blocks.add(bi)
            groups = []
            current = []
            last_key = None
            for r in regular:
                x0, _, x1, _ = r['bbox']
                col = 'single' if gutter is None else ('wide' if r['block'] in wide_blocks else 'left' if x1 <= gutter + 3 else 'right' if x0 >= gutter - 3 else 'wide')
                key = (r['block'], col)
                gap = current and r['bbox'][1] - current[-1]['bbox'][3] > body_size * .85
                if current and (key != last_key or gap):
                    groups.append((last_key[1], current))
                    current = []
                current.append(r)
                last_key = key
            if current:
                groups.append((last_key[1], current))
            blocks = []
            for column, lines in groups:
                text = tidy_lines(lines)
                if not text:
                    continue
                box = [min(l['bbox'][0] for l in lines), min(l['bbox'][1] for l in lines),
                       max(l['bbox'][2] for l in lines), max(l['bbox'][3] for l in lines)]
                kind = classify(text, lines, body_size)
                confidence = 'check' if len(text) < 24 and kind == 'paragraph' else 'normal'
                if any(abs(l['dir'][1]) > .05 for l in lines):
                    confidence = 'check'
                digest = hashlib.sha256((str(pi) + repr([round(x, 2) for x in box]) + text).encode()).hexdigest()[:16]
                blocks.append({'id': f'p{pi + 1}-{digest}', 'page': pi, 'text': text, 'kind': kind,
                               'column': column, 'confidence': confidence, 'source_bbox': box,
                               'bbox': normalized_rect(box, page),
                               'line_boxes': [normalized_rect(l['bbox'], page) for l in lines],
                               'math_runs': inline_math(lines,text,page,normalized_rect),
                               'excluded': False})
                if kind=='equation':
                    blocks[-1]['source_only']=True
                    blocks[-1]['math_clip_boxes']=formula_clip_boxes(lines,page,normalized_rect,box)
            for ri,(kind,box) in enumerate(regions):
                column = 'single' if gutter is None else 'left' if box[2] <= gutter+3 else 'right' if box[0]>=gutter-3 else 'wide'
                text = tidy_lines(region_text[ri])
                digest = hashlib.sha256((str(pi)+kind+repr(box)).encode()).hexdigest()[:16]
                blocks.append({'id':f'p{pi+1}-{digest}','page':pi,'text':text or ('图像区域' if kind=='figure' else '表格区域'),
                               'kind':kind,'column':column,'confidence':'source','source_bbox':box,
                               'bbox':normalized_rect(box,page),'line_boxes':[], 'excluded':False,
                               'source_only':True})
                if kind=='equation':blocks[-1]['math_clip_boxes']=formula_clip_boxes(region_text[ri],page,normalized_rect,box)
            blocks = order_blocks(blocks, gutter)
            for b in blocks:
                b['order'] = order
                order += 1
                fulltext.append(b['text'])
            chars = sum(len(b['text']) for b in blocks)
            warnings = []
            if chars < 60:
                warnings.append('该页可提取文字很少，可能是扫描页或图表页。本版未内置 OCR，请在原页核对。')
            if any(b['confidence'] == 'check' for b in blocks):
                warnings.append('存在短片段或旋转文字，可能来自图表。可排除片段或调整顺序。')
            pages.append({'index': pi, 'width': page.rect.width, 'height': page.rect.height,
                          'rotation': page.rotation, 'layout': 'two-column' if gutter else 'single-column',
                          'gutter': round(gutter / width, 4) if gutter else None, 'layout_score': score,
                          'blocks': blocks, 'warnings': warnings, 'ignored_margin_lines': len(excluded)})
        return {'parser_version': PARSER_VERSION, 'coordinate_space': 'rendered_page_normalized',
                'pages': pages, 'page_count': len(pages), 'block_count': order,
                'text_character_count': sum(map(len, fulltext)),
                'note': '本地文本优先解析；双栏顺序为规则推断。图表和公式以原页为准，扫描件需另加 OCR。'}
