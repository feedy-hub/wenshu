"""Durable, bounded rewrite tasks; no conversation history accumulates between items."""
import json
import time
import uuid
import writing
import languages
import context_manager as context

ACTIVE=('queued','running')


def manuscript_hash(doc):
    return context.digest([(b['id'],b['text'],b.get('excluded',False),b.get('layout_ignored')) for p in doc.get('pages',[]) for b in p['blocks']])


def plan(doc,instruction='',options=None):
    opts=context.settings(doc,options)
    grouped={};skipped=[]
    blocks={b['id']:b for p in doc.get('pages',[]) for b in p['blocks']}
    for note in doc.get('annotations',[]):
        if note.get('status')!='open':continue
        b=blocks.get(note['block_id'])
        reason=None
        if not b:reason='原段落已失效'
        elif b.get('source_only') or b.get('excluded') or b.get('layout_ignored') or b['id'] in opts['excludes']:reason='已排除或不属于可改写正文'
        else:
            try:writing.anchor(b,note)
            except ValueError as e:reason=str(e)
        if reason:skipped.append({'note_id':note['id'],'reason':reason});continue
        grouped.setdefault(b['id'],[]).append(note)
    items=[];source_hash=manuscript_hash(doc)
    for bid,b in blocks.items():
        notes=sorted(grouped.get(bid,[]),key=lambda n:(n['start'],n['end']))
        units=[]
        for note in notes:
            if units and note['start']<units[-1]['end']:
                units[-1]['end']=max(units[-1]['end'],note['end']);units[-1]['notes'].append(note)
            else:units.append({'start':note['start'],'end':note['end'],'notes':[note]})
        for unit in units:
            anchor=writing.anchor(b,{k:unit[k] for k in ('start','end')})
            notes=[{'id':n['id'],'body':n['body'],'kind':n.get('kind','')} for n in unit['notes']]
            key=context.digest([source_hash,anchor,notes,instruction,opts])
            items.append({**anchor,'notes':notes,'key':key,'status':'pending','attempts':0})
    if len(items)>500:raise ValueError('单批最多处理 500 个选区，请分批处理。')
    fingerprint=context.digest([source_hash,[i['key'] for i in items],instruction,opts,skipped])
    return {'fingerprint':fingerprint,'source_hash':source_hash,'items':items,'skipped':skipped,'options':opts,
            'instruction':instruction,'annotation_count':sum(len(i['notes']) for i in items),'total':len(items),
            'input_upper_estimate':len(items)*opts['budget']}


def load(app,bid):
    with app.connect() as c:r=c.execute('SELECT data FROM rewrite_batches WHERE id=?',(bid,)).fetchone()
    if not r:raise ValueError('未找到批量任务。')
    return json.loads(r['data'])


def save(app,batch,connection=None):
    batch['updated']=time.time()
    args=(batch['id'],batch['document_id'],json.dumps(batch,ensure_ascii=False),batch['updated'])
    if connection is not None:connection.execute('INSERT OR REPLACE INTO rewrite_batches VALUES (?,?,?,?)',args)
    else:
        with app.connect() as c:c.execute('INSERT OR REPLACE INTO rewrite_batches VALUES (?,?,?,?)',args)


def check_source(app,doc):
    if doc.get('project_id') and app.latex_project.load(app.DATA,doc['project_id'])['revision']!=doc['project_revision']:
        raise ValueError('源稿已修改，请先编译并打开新版 PDF 后再批量改写。')


def create(app,doc,data,config):
    instruction=str(data.get('instruction','')).strip()
    if len(instruction)>8000:raise ValueError('统一要求不能超过 8000 字。')
    check_source(app,doc)
    task=plan(doc,instruction,data.get('context_options'))
    if not task['items']:raise ValueError('没有可处理的待办批注。请先选择原句并保存批注。')
    if data.get('fingerprint')!=task['fingerprint']:raise ValueError('批注或上下文设置已变化，请重新查看任务计划。')
    limit=int(data.get('input_limit',128000))
    if not task['options']['budget']<=limit<=2000000:raise ValueError('本批预算需不小于单项预算，且最多为 200 万 token。')
    with app.connect() as c:
        previous=[json.loads(r['data']) for r in c.execute('SELECT data FROM rewrite_batches WHERE document_id=? ORDER BY updated DESC',(doc['id'],))]
    for prior in previous:
        if prior['fingerprint']==task['fingerprint'] and prior['model']==config['model'] and prior['base_url']==config['base_url'] and prior.get('source', languages.DEFAULT_SOURCE)==config.get('source', languages.DEFAULT_SOURCE) and prior.get('target', languages.DEFAULT_TARGET)==config.get('target', languages.DEFAULT_TARGET):
            return prior
    if any(prior['status'] in ACTIVE for prior in previous):raise ValueError('该论文已有运行中的批量任务，请先完成或停止。')
    for item in task['items']:
        key=context.digest([item['key'],config['base_url'],config['model'],config.get('source', languages.DEFAULT_SOURCE),config.get('target', languages.DEFAULT_TARGET)])
        item['request_key']=key
        cached=next((p for p in reversed(doc.get('proposals',[])) if p.get('batch_request_key')==key and p['status']=='proposed'),None)
        if cached:item.update(status='done',proposal_id=cached['id'],reused=True)
    batch={**task,'id':uuid.uuid4().hex,'document_id':doc['id'],'status':'queued','created':time.time(),
           'model':config['model'],'base_url':config['base_url'],'source':config.get('source', languages.DEFAULT_SOURCE),'target':config.get('target', languages.DEFAULT_TARGET),'input_limit':limit,'reserved_tokens':0,
           'reported_input_tokens':0,'reported_output_tokens':0,'reported_calls':0,'error':''}
    save(app,batch);return batch


def unchanged(doc,batch):
    return plan(doc,batch['instruction'],batch['options'])['fingerprint']==batch['fingerprint']


def run(app,bid,config,cancel):
    batch=load(app,bid);batch['status']='running';save(app,batch)
    config={**config,'source':batch.get('source', languages.DEFAULT_SOURCE),'target':batch.get('target', languages.DEFAULT_TARGET)}
    try:
        for item in batch['items']:
            if item['status']=='done':continue
            if cancel.is_set():batch['status']='cancelled';break
            doc=app.load_doc(batch['document_id'])
            check_source(app,doc)
            if not unchanged(doc,batch):batch.update(status='conflict',error='批注或正文已变化，已停止。已生成建议保留，请重新建立任务。');break
            block=app.find_block(doc,item['block_id'])
            data={k:item[k] for k in ('start','end','quote')}
            data.update(instruction=batch['instruction'],context_options=batch['options'])
            try:
                package=context.build(doc,block,data,config,app.context_cached)
                estimated=package['estimated_input_tokens']
                if batch['reserved_tokens']+estimated>batch['input_limit']:
                    batch.update(status='budget_paused',error='已达到本批预算上限，追加预算后可继续。');break
                # Persist before dispatch, so a crash cannot silently reset spending.
                item.update(status='running',error='',attempts=item['attempts']+1)
                batch['reserved_tokens']+=estimated;save(app,batch)
                config.pop('_last_usage',None)
                proposal=writing.build_proposal(doc,block,{**data,'context_package':package},config,app.request_completion)
                usage=config.get('_last_usage',{})
                if isinstance(usage.get('prompt_tokens'),int):
                    batch['reported_input_tokens']+=usage['prompt_tokens'];batch['reported_output_tokens']+=usage.get('completion_tokens',0);batch['reported_calls']+=1
                proposal.update(batch_id=bid,batch_request_key=item['request_key'],usage=usage)
                with app.DB_LOCK:
                    live=app.load_doc(doc['id']);check_source(app,live)
                    if not unchanged(live,batch):raise ValueError('请求期间批注或正文已变化，本项结果未写入。')
                    live['proposals'].append(proposal);item.update(status='done',proposal_id=proposal['id'])
                    with app.connect() as c:
                        c.execute('UPDATE documents SET data=? WHERE id=?',(json.dumps(live,ensure_ascii=False),live['id']))
                        save(app,batch,c)
            except Exception as e:
                item.update(status='failed',error=app.safe_error(e,config));save(app,batch)
                if any('HTTP '+code in item['error'] for code in ('401','402','403','429')):
                    batch.update(status='partial',error='服务商拒绝了请求，已停止后续调用。请检查 API 设置或额度后继续。');break
        if batch['status']=='running':
            batch['status']='cancelled' if cancel.is_set() else 'partial' if any(i['status']=='failed' for i in batch['items']) else 'completed'
    except Exception as e:batch.update(status='conflict',error=app.safe_error(e,config))
    finally:
        for item in batch['items']:
            if item['status']=='running':item['status']='pending'
        save(app,batch)


def selected_proposals(doc,batch,ids):
    if batch['status'] in ACTIVE:raise ValueError('请等待批量生成完成或停止任务后再写入。')
    if not isinstance(ids,list) or not ids:raise ValueError('请选择要写入的建议。')
    available={i.get('proposal_id') for i in batch['items'] if i['status']=='done'}
    proposals={p['id']:p for p in doc.get('proposals',[])}
    result=[]
    for pid in dict.fromkeys(ids):
        if pid not in available or pid not in proposals:raise ValueError('所选建议不属于此批次。')
        p=proposals[pid]
        if p['status']!='proposed':raise ValueError('有建议已处理，请刷新批次。')
        b=next(b for page in doc['pages'] for b in page['blocks'] if b['id']==p['block_id'])
        if writing.digest(b['text'])!=p['text_hash']:raise ValueError('原文已变化，请重新生成。')
        result.append(p)
    return result
