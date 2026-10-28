"""Local source copies, isolated compilation and conservative literal mapping."""
import io
import json
import os
import re
import shutil
import subprocess
import uuid
import hashlib
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath


PROJECT_EXTENSIONS={'.tex','.bib','.cls','.sty','.bst','.bbl','.png','.jpg','.jpeg','.pdf','.eps','.svg','.csv','.dat','.txt','.pgf','.tikz'}

def directory(data, pid):
    if not re.fullmatch(r'[a-f0-9]{32}', pid): raise ValueError('无效项目。')
    return data / 'projects' / pid

def load(data,pid):
    return json.loads((directory(data,pid)/'meta.json').read_text(encoding='utf-8'))

def save(data,meta):
    (directory(data,meta['id'])/'meta.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf-8')

def create(data,raw,name):
    if name.lower().endswith('.tex'):
        return create_files(data,[('main.tex',raw)],name)
    if not name.lower().endswith('.zip'):raise ValueError('请导入 .tex、项目 ZIP 或文件夹。')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            infos=[f for f in z.infolist() if not f.is_dir() and Path(f.filename).suffix.lower() in PROJECT_EXTENSIONS and '__MACOSX' not in PurePosixPath(f.filename).parts]
            if len(z.infolist())>2000 or sum(f.file_size for f in infos)>150*1024*1024:raise ValueError('项目超过 2000 个文件或 150 MB 限制。')
            if any((f.external_attr>>16)&0o170000==0o120000 for f in infos):raise ValueError('项目包含符号链接，无法导入。')
            return create_files(data,[(f.filename,z.read(f)) for f in infos],name)
    except zipfile.BadZipFile:raise ValueError('ZIP 文件损坏或格式无效。') from None


def create_files(data,files,name):
    if not files or len(files)>2000 or sum(len(content) for _,content in files)>150*1024*1024:
        raise ValueError('项目为空，或超过 2000 个文件、150 MB 限制。')
    paths=[]
    for filename,content in files:
        if not isinstance(filename,str) or not isinstance(content,bytes):raise ValueError('项目文件无效。')
        p=PurePosixPath(filename)
        if p.is_absolute() or '..' in p.parts or ':' in filename or '\\' in filename or not p.parts or p.suffix.lower() not in PROJECT_EXTENSIONS:
            raise ValueError('项目包含不安全或不支持的文件路径。')
        paths.append(p)
    shared=paths[0].parts[0] if all(len(p.parts)>1 and p.parts[0]==paths[0].parts[0] for p in paths) else None
    relative=[PurePosixPath(*p.parts[1:]) if shared else p for p in paths]
    if len(set(relative))!=len(relative):raise ValueError('项目中存在重名文件。')
    candidates=[p.as_posix() for p,(_,content) in zip(relative,files) if p.suffix.lower()=='.tex' and '\\documentclass' in content.decode('utf-8',errors='replace')]
    if not candidates:raise ValueError('没有找到包含 documentclass 的主文件。')
    candidates.sort(key=lambda p:(len(PurePosixPath(p).parts),PurePosixPath(p).name.lower()!='main.tex',p))
    pid=uuid.uuid4().hex
    root=directory(data,pid);source=root/'source';source.mkdir(parents=True)
    for p,(_,content) in zip(relative,files):
        dest=source/Path(p.as_posix());dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(content)
    main_text=(source/candidates[0]).read_text(encoding='utf-8',errors='replace')
    preferred='xelatex' if re.search(r'\\(?:usepackage\{fontspec\}|setmainfont|documentclass(?:\[[^]]*\])?\{ctex)',main_text) else 'pdflatex'
    meta={'id':pid,'name':name,'main_file':candidates[0],'candidates':candidates,'file_count':len(files),'preferred_engine':preferred,'revision':1,'history':[]}
    meta['missing_files']=missing_dependencies(source,candidates[0])
    save(data,meta);return meta


def missing_dependencies(source,main):
    work=source/Path(main).parent
    text=(source/main).read_text(encoding='utf-8',errors='replace')
    missing=[]
    for path in re.findall(r'\\includegraphics(?:\[[^]]*\])?\s*\{([^{}]+)\}',text):
        if '\\' in path or '#' in path:continue
        choices=[path] if Path(path).suffix else [path+ext for ext in ('.pdf','.png','.jpg','.jpeg','.eps')]
        if not any((work/choice).is_file() for choice in choices):missing.append(path)
    for group in re.findall(r'\\bibliography\s*\{([^{}]+)\}',text):
        for value in group.split(','):
            path=value.strip()+('.bib' if not value.strip().endswith('.bib') else '')
            if path and not (work/path).is_file():missing.append(path)
    return list(dict.fromkeys(missing))


def active_tex_files(source, main):
    """Only the selected main file and its input/include tree belong to this PDF."""
    root=source.resolve();seen=set();pending=[root/main]
    while pending:
        path=pending.pop().resolve()
        if not path.is_relative_to(root) or not path.is_file() or path in seen:continue
        seen.add(path)
        visible=re.sub(r'(?<!\\)%[^\n]*','',path.read_text(encoding='utf-8',errors='replace'))
        for name in re.findall(r'\\(?:input|include)\s*\{([^{}]+)\}',visible):
            if '\\' in name or ':' in name:continue
            target=Path(name if name.endswith('.tex') else name+'.tex')
            for base in (path.parent,root/Path(main).parent):
                candidate=(base/target).resolve()
                if candidate.is_relative_to(root) and candidate.is_file():
                    pending.append(candidate);break
    return sorted(seen)

def compile_project(data,pid,main=None,engine='pdflatex'):
    meta=load(data,pid);root=directory(data,pid)
    if main and main not in meta['candidates']: raise ValueError('主文件不在项目候选列表中。')
    if engine not in ('pdflatex','xelatex','lualatex'): raise ValueError('编译器无效。')
    exe=shutil.which(engine) or str(Path('D:/latex-ai-workbench/tools/TinyTeX/TinyTeX/bin/windows')/(engine+'.exe'))
    if not Path(exe).exists(): raise ValueError('未找到本地 LaTeX 编译器，请安装 TinyTeX 或 TeX Live。')
    main=main or meta['main_file'];meta['main_file']=main
    missing=missing_dependencies(root/'source',main)
    if missing:raise ValueError('项目缺少编译文件：'+', '.join(missing[:8])+(' 等' if len(missing)>8 else '')+'。请导入完整文件夹或 ZIP。')
    build=root/'builds'/uuid.uuid4().hex;shutil.copytree(root/'source',build)
    work=build/Path(main).parent
    env=dict(os.environ,openin_any='p',openout_any='p')
    log=''
    for pass_number in range(3):
        try:
            result=subprocess.run([exe,'-no-shell-escape','-interaction=nonstopmode','-halt-on-error','-file-line-error','-synctex=1','-jobname=manuscript',Path(main).name],cwd=work,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=75,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except subprocess.TimeoutExpired: raise ValueError('编译超过 75 秒，已停止。') from None
        log+=result.stdout.decode('utf-8',errors='replace')
        (root/'last-compile.log').write_text(log,encoding='utf-8')
        if result.returncode: raise ValueError('编译失败：'+log[-2200:])
        if pass_number==0 and re.search(r'\\bibliography\s*\{', (root/'source'/main).read_text(encoding='utf-8',errors='replace')):
            bibtex=shutil.which('bibtex') or str(Path('D:/latex-ai-workbench/tools/TinyTeX/TinyTeX/bin/windows/bibtex.exe'))
            if not Path(bibtex).exists():raise ValueError('项目使用 BibTeX，但本机未找到 bibtex 编译器。')
            try:
                citations=subprocess.run([bibtex,'manuscript'],cwd=work,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=45,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            except subprocess.TimeoutExpired:raise ValueError('参考文献编译超过 45 秒，已停止。') from None
            log+=citations.stdout.decode('utf-8',errors='replace')
            (root/'last-compile.log').write_text(log,encoding='utf-8')
            if citations.returncode:raise ValueError('BibTeX 编译失败：'+log[-2200:])
    save(data,meta)
    return meta,(work/'manuscript.pdf').read_bytes()

def normalized_source(text):
    chars=[];offsets=[];i=0
    while i<len(text):
        c=text[i]
        if c=='\u00ad':i+=1;continue
        if c in '-‐‑' and i>0 and text[i-1].isalpha():
            j=i+1
            while j<len(text) and text[j].isspace():j+=1
            if j<len(text) and text[j].isalpha():i=j;continue
        if c.isspace():
            if chars and chars[-1]!=' ':chars.append(' ');offsets.append(i)
        else:
            c={'’':"'",'‘':"'",'“':'"','”':'"'}.get(c,c)
            for value in unicodedata.normalize('NFKC',c):chars.append(value);offsets.append(i)
        i+=1
    return ''.join(chars),offsets


def locate(data,pid,quote):
    meta=load(data,pid);source=(directory(data,pid)/'source').resolve()
    needle,_=normalized_source(quote.strip())
    if not needle:raise ValueError('选中的原文为空，请重新选择。')
    found=[]
    for p in active_tex_files(source,meta['main_file']):
        raw=p.read_text(encoding='utf-8')
        # Hide comments without changing character offsets.
        visible=re.sub(r'(?<!\\)%[^\n]*',lambda m:' '*len(m.group()),raw)
        normalized,offsets=normalized_source(visible)
        pos=0
        while True:
            at=normalized.find(needle,pos)
            if at<0:break
            pos=at+1
            if (at and normalized[at-1].isalnum() and needle[0].isalnum()) or (at+len(needle)<len(normalized) and normalized[at+len(needle)].isalnum() and needle[-1].isalnum()):continue
            start,end=offsets[at],offsets[at+len(needle)-1]+1
            before=raw[start:end]
            if any(c in before for c in '\\{}$%'):continue
            # Do not replace arguments of LaTeX commands or math environments.
            prefix=visible[:start]
            document_start=prefix.find('\\begin{document}')
            if document_start<0:continue
            prefix=prefix[document_start+len('\\begin{document}'):]
            if prefix.count('{')!=prefix.count('}') or len(re.findall(r'(?<!\\)\$',prefix))%2:continue
            math_open=False
            for token in re.finditer(r'\\(\\|[\[\]()])',prefix):
                if token[1] in ('[','('):math_open=True
                elif token[1] in (']',')'):math_open=False
            if math_open:continue
            stack=[]
            for env in re.finditer(r'\\(begin|end)\{([^}]+)\}',prefix):
                if env[1]=='begin':stack.append(env[2])
                elif stack and stack[-1]==env[2]:stack.pop()
            if any(e not in ('document','abstract','quote','quotation','itemize','enumerate') for e in stack):continue
            found.append({'file':p.relative_to(source).as_posix(),'start':start,'end':end,'raw_before':before,'line':raw[:start].count('\n')+1,'revision':meta['revision'],'match_mode':'typography-normalized'})
    if not found:
        from source_mapping import structured_matches
        found=structured_matches(source,quote,meta['revision'],normalized_source,active_tex_files(source,meta['main_file']))
    if len(found)!=1: return {'available':False,'reason':'源稿中无法唯一匹配纯文本（可能含宏、公式或重复句子），请导出建议人工处理。'}
    return {'available':True,**found[0]}


def read_source(data,pid,file=None):
    meta=load(data,pid);root=(directory(data,pid)/'source').resolve()
    files=sorted(p.relative_to(root).as_posix() for p in root.rglob('*.tex') if p.is_file())
    file=file or meta['main_file']
    path=(root/file).resolve()
    if not path.is_relative_to(root) or file not in files:raise ValueError('请选择项目内的 .tex 文件。')
    if path.stat().st_size>2*1024*1024:raise ValueError('源文件超过编辑器的 2 MB 限制。')
    text=path.read_text(encoding='utf-8')
    return {'project':meta,'files':files,'file':file,'text':text,'hash':hashlib.sha256(text.encode()).hexdigest()}


def edit_source(data,pid,file,text,expected_revision,expected_hash):
    current=read_source(data,pid,file);meta=current['project']
    if meta['revision']!=expected_revision or current['hash']!=expected_hash:raise ValueError('源稿已变化，请重新打开编辑器后再保存。')
    if not isinstance(text,str) or len(text.encode())>2*1024*1024:raise ValueError('源文件内容无效或超过 2 MB。')
    if text==current['text']:return meta
    root=directory(data,pid);path=root/'source'/file
    history=root/'history';history.mkdir(exist_ok=True)
    backup=f"{meta['revision']}-manual-{uuid.uuid4().hex}.tex"
    (history/backup).write_text(current['text'],encoding='utf-8')
    temporary=path.with_suffix('.tex.tmp');temporary.write_text(text,encoding='utf-8');temporary.replace(path)
    meta['revision']+=1;meta['history'].append({'source':'manual-editor','file':file,'backup':backup})
    save(data,meta);return meta

def apply(data,pid,proposal,expected_revision):
    meta=load(data,pid)
    if meta['revision']!=expected_revision:raise ValueError('源稿版本已改变，请重新编译后再改写。')
    match=locate(data,pid,proposal['quote'])
    if not match['available']:raise ValueError(match['reason'])
    path=directory(data,pid)/'source'/match['file'];raw=path.read_text(encoding='utf-8')
    escape={'\\':r'\textbackslash{}','&':r'\&','%':r'\%','$':r'\$','#':r'\#','_':r'\_','{':r'\{','}':r'\}','~':r'\textasciitilde{}','^':r'\textasciicircum{}'}
    from source_mapping import replacement_source
    replacement=replacement_source(proposal['replacement'],match,escape)
    history=directory(data,pid)/'history';history.mkdir(exist_ok=True)
    (history/(str(meta['revision'])+'-'+path.name)).write_text(raw,encoding='utf-8')
    path.write_text(raw[:match['start']]+replacement+raw[match['end']:],encoding='utf-8')
    meta['revision']+=1;meta['history'].append({'proposal_id':proposal['id'],'file':match['file'],'before':match['raw_before'],'after':replacement})
    save(data,meta);return meta

def export(data,pid):
    root=directory(data,pid);out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for p in (root/'source').rglob('*'):
            if p.is_file():z.write(p,p.relative_to(root/'source'))
        z.writestr('shore-history.json',(root/'meta.json').read_bytes())
    return out.getvalue()


def batch_matches(data,pid,proposals,expected_revision):
    if load(data,pid)['revision']!=expected_revision:raise ValueError('源稿版本已变化，请先重新编译。')
    matches=[]
    for proposal in proposals:
        match=locate(data,pid,proposal['quote'])
        if match.get('available'):
            from source_mapping import replacement_source
            try:replacement_source(proposal['replacement'],match,{})
            except ValueError as e:match={'available':False,'reason':str(e)}
        matches.append({**match,'proposal_id':proposal['id']})
    for i,a in enumerate(matches):
        if not a.get('available'):continue
        for b in matches[i+1:]:
            if b.get('available') and a['file']==b['file'] and a['start']<b['end'] and b['start']<a['end']:
                raise ValueError('有建议对应的源稿范围重叠，请只选择其中一条。')
    return matches


def apply_batch(data,pid,proposals,expected_revision):
    """Validate everything first, then replace in reverse offset order, one revision."""
    import copy
    matches=batch_matches(data,pid,proposals,expected_revision)
    if any(not m.get('available') for m in matches):raise ValueError('部分建议无法安全定位，本次未写入任何建议。')
    meta=load(data,pid);original_meta=copy.deepcopy(meta);root=directory(data,pid)
    grouped={};originals={};outputs={};history=root/'history';history.mkdir(exist_ok=True)
    escape={'\\':r'\textbackslash{}','&':r'\&','%':r'\%','$':r'\$','#':r'\#','_':r'\_','{':r'\{','}':r'\}','~':r'\textasciitilde{}','^':r'\textasciicircum{}'}
    for proposal,match in zip(proposals,matches):grouped.setdefault(match['file'],[]).append((proposal,match))
    for file,items in grouped.items():
        raw=(root/'source'/file).read_text(encoding='utf-8');originals[file]=raw;updated=raw
        for proposal,match in sorted(items,key=lambda pair:pair[1]['start'],reverse=True):
            if raw[match['start']:match['end']]!=match['raw_before']:raise ValueError('源文件内容已变化，本次未写入。')
            from source_mapping import replacement_source
            replacement=replacement_source(proposal['replacement'],match,escape)
            updated=updated[:match['start']]+replacement+updated[match['end']:]
            meta['history'].append({'proposal_id':proposal['id'],'file':file,'before':match['raw_before'],'after':replacement,'source':'batch'})
        outputs[file]=updated
    # Every original file is backed up before the first source file is replaced.
    for file,raw in originals.items():
        backup=f"{expected_revision}-batch-{uuid.uuid4().hex}.tex"
        (history/backup).write_text(raw,encoding='utf-8')
        meta['history'].append({'source':'batch-backup','file':file,'backup':backup})
    written=[]
    try:
        for file,updated in outputs.items():
            path=root/'source'/file;temporary=path.with_suffix('.tex.batch-tmp')
            temporary.write_text(updated,encoding='utf-8');temporary.replace(path);written.append(file)
        meta['revision']+=1;save(data,meta)
    except Exception:
        for file in written:(root/'source'/file).write_text(originals[file],encoding='utf-8')
        save(data,original_meta)
        raise
    return meta
