"""Conservative PDF math detection; render original glyphs rather than guessed TeX."""
import re
import statistics
import math
import pymupdf as fitz

MATH_FONT=re.compile(r'(?:CMMI|CMSY|CMEX|MSAM|MSBM|Math|STIX|Symbol|CMBSY|CMBXTI|txsy|txmi|txex)',re.I)
OPERATORS={'exp','log','ln','sin','cos','tan','max','min','arg','sg','LN','FFN','MHA','softmax','lim','det','Re','Im'}

def is_math(span):
    return bool(MATH_FONT.search(span.get('font','')))

def annotate_row(row,spans):
    row['spans']=spans
    row['math_chars']=sum(len(s['text'].strip()) for s in spans if is_math(s))
    words=[]
    for s in spans:
        if not is_math(s):words.extend(w for w in re.findall(r'[A-Za-z]{2,}',s['text']) if w not in OPERATORS)
    row['prose_words']=len(words)


def merge_inline_rows(rows):
    """MuPDF may split a superscript/subscript into another block on the same line."""
    merged=[];parents={}
    def root(n):
        while n in parents:n=parents[n]
        return n
    for row in rows:
        prev=merged[-1] if merged else None
        if prev:
            a=fitz.Rect(prev['bbox']);b=fitz.Rect(row['bbox'])
            overlap=min(a.y1,b.y1)-max(a.y0,b.y0)
            near=-max(prev['size'],row['size'])*.8<=b.x0-a.x1<=max(prev['size'],row['size'])*1.2
            if (prev['math_chars'] or row['math_chars']) and overlap>min(a.height,b.height)*.45 and b.x0>=a.x0 and near:
                spans=prev['spans']+row['spans']
                prev['text']=''.join(s['text'] for s in spans).strip()
                prev['bbox']=list(a|b)
                if root(row['block'])!=root(prev['block']):parents[root(row['block'])]=root(prev['block'])
                annotate_row(prev,spans)
                continue
        merged.append(row)
    for row in merged:row['block']=root(row['block'])
    return merged

def equation_regions(rows,gutter,width,body_size):
    regions=[]
    columns=('left','right') if gutter else ('single',)
    def column(r):
        x0,_,x1,_=r['bbox']
        return 'single' if gutter is None else 'left' if x1<=gutter+3 else 'right' if x0>=gutter-3 else 'wide'
    for col in columns:
        items=[r for r in rows if column(r)==col and not (re.fullmatch(r'\d{1,5}',r['text']) and (r['bbox'][2]<width*.09 or r['bbox'][0]>width*.93))]
        prose=[r for r in items if r['prose_words']>=2 or r['prose_words'] and not r['math_chars']]
        candidates=[r for r in items if r not in prose and (r['math_chars'] or re.fullmatch(r'[\s\d().,;:+−=\[\]{}|a-zA-Z]*',r['text']) and len(r['text'])<35)]
        groups=[]
        for r in sorted(candidates,key=lambda r:r['bbox'][1]):
            # Inline variables share a vertical band with prose and stay inline.
            center=(r['bbox'][1]+r['bbox'][3])/2
            if any(p['bbox'][1]-1<=center<=p['bbox'][3]+1 for p in prose):continue
            last=groups[-1] if groups else []
            bottom=max((x['bbox'][3] for x in last),default=-100)
            start=min((x['bbox'][1] for x in last),default=-100)
            blocked=any(start<p['bbox'][1]<r['bbox'][1] for p in prose)
            if last and r['bbox'][1]-bottom<=body_size*.85 and not blocked:last.append(r)
            else:groups.append([r])
        for group in groups:
            text=' '.join(r['text'] for r in group)
            if not any(r['math_chars'] for r in group) and not re.search(r'[=∑∫≈≤≥∂√]',text):continue
            # Avoid capturing an isolated variable or a short heading as a display.
            if not re.search(r'[=∑∫≈≤≥∂√]|\(\d+\)',text) and sum(r['math_chars'] for r in group)<4:continue
            box=fitz.Rect(min(r['bbox'][0] for r in group)-1.5,min(r['bbox'][1] for r in group)-1.5,max(r['bbox'][2] for r in group)+1.5,max(r['bbox'][3] for r in group)+1.5)
            regions.append(('equation',list(box)))
    return regions


def formula_clip_boxes(lines,page,normalize,region):
    boxes=[normalize(fitz.Rect(s['bbox'])+(-.15,-.2,.15,.2),page) for row in lines for s in row.get('spans',[]) if s['text'].strip()]
    # Fraction bars and radical rules are vector paths, not text glyphs.
    outer=fitz.Rect(region)+(-1,-1,1,1)
    for drawing in page.get_drawings():
        box=fitz.Rect(drawing['rect'])+(-.5,-.5,.5,.5)
        if outer.contains(box):boxes.append(normalize(box,page))
    return boxes

def line_character_map(lines,text):
    """Mirror tidy_lines while retaining the PDF span offsets through dehyphenation."""
    chars=[]
    for li,line in enumerate(lines):
        raw=''.join(s['text'] for s in line.get('spans',[]))
        stripped=raw.strip()
        if not stripped:continue
        if stripped!=line['text'].strip():return None
        trim=len(raw)-len(raw.lstrip())
        if len(chars)>1 and chars[-1][0]=='-' and chars[-2][0].isalpha() and stripped[0].islower():chars.pop()
        elif chars:chars.append((' ',None,None))
        chars.extend((c,li,trim+i) for i,c in enumerate(stripped))
    normalized=[];mapping={}
    for c,li,ri in chars:
        if c.isspace():
            if not normalized or normalized[-1]==' ':continue
            c=' '
        if li is not None:mapping[(li,ri)]=len(normalized)
        normalized.append(c)
    if ''.join(normalized).strip()!=text:return None
    return mapping


def inline_math(lines,text,page,normalize):
    """Offsets refer to unchanged normalized paragraph text; uncertain matches skipped."""
    runs=[];mapping=line_character_map(lines,text)
    if mapping is None:return runs
    for li,line in enumerate(lines):
        spans=line.get('spans',[]);raw=''.join(s['text'] for s in spans)
        prose=[s for s in spans if not is_math(s) and re.search(r'[A-Za-z]{2,}',s['text'])]
        size=statistics.median(s['size'] for s in prose) if prose else max((s['size'] for s in spans),default=line['size'])
        base_spans=prose or [s for s in spans if abs(s['size']-size)<.3]
        baseline=statistics.median(s['origin'][1] for s in base_spans) if base_spans else line['bbox'][3]
        offsets=[];pos=0
        for s in spans:offsets.append((pos,pos+len(s['text'])));pos+=len(s['text'])
        marked=[is_math(s) and bool(s['text'].strip()) for s in spans]
        # Include small superscripts, digits and brackets adjacent to mathematical fonts.
        for i,s in enumerate(spans):
            if marked[i]:continue
            if re.fullmatch(r'[\s\d.,;:()\[\]{}+−=|^_ˆ˜¯˙]*',s['text']) or s['text'].strip() in OPERATORS:
                if i>0 and marked[i-1] or i+1<len(spans) and is_math(spans[i+1]):marked[i]=True
        i=0
        while i<len(spans):
            if not marked[i]:i+=1;continue
            j=i+1
            while j<len(spans) and (marked[j] or spans[j]['text'].isspace() and j+1<len(spans) and marked[j+1]):j+=1
            a=offsets[i][0];b=offsets[j-1][1]
            while a<b and raw[a].isspace():a+=1
            while b>a and raw[b-1].isspace():b-=1
            positions=[mapping[(li,k)] for k in range(a,b) if (li,k) in mapping]
            if positions:
                ink=[s for s in spans[i:j] if s['text'].strip()]
                box=fitz.Rect(ink[0]['bbox'])
                for s in ink[1:]:box|=fitz.Rect(s['bbox'])
                # Whitespace boxes reach the neighboring prose glyph; exclude them.
                box=fitz.Rect(box.x0-.05,box.y0-.2,box.x1+.05,box.y1+.2)
                start,end=min(positions),max(positions)+1
                clips=[normalize(fitz.Rect(s['bbox'])+(-.05,-.2,.05,.2),page) for s in ink]
                runs.append({'start':start,'end':end,'text':text[start:end],'bbox':normalize(box,page),'clip_boxes':clips,'width':box.width,'height':box.height,'size':size,'baseline_offset':baseline-box.y1})
            i=j
    return runs


def mask_formula_crop(pix,page,run,scale=3):
    """Keep only formula spans, excluding nearby prose caught by the enclosing box."""
    boxes=run.get('clip_boxes')
    if not boxes:return pix
    regions=[(math.floor(b[0]*page.rect.width*scale),math.floor(b[1]*page.rect.height*scale),
              math.ceil(b[2]*page.rect.width*scale),math.ceil(b[3]*page.rect.height*scale)) for b in boxes]
    for y in range(pix.y,pix.y+pix.height):
        intervals=sorted((max(pix.x,a),min(pix.x+pix.width,c)) for a,b,c,d in regions if b<=y<d)
        at=pix.x
        for left,right in intervals:
            if left>at:pix.set_rect(fitz.IRect(at,y,left,y+1),(255,255,255))
            at=max(at,right)
        if at<pix.x+pix.width:pix.set_rect(fitz.IRect(at,y,pix.x+pix.width,y+1),(255,255,255))
    return pix
