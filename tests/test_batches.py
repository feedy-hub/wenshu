import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
import app
import batch_rewrite as batch
import latex_project as lp
import writing


def paper():
    text='The first result is stable. The second result is reliable. The third result is useful.'
    b={'id':'b','page':0,'kind':'paragraph','text':text,'excluded':False}
    doc={'id':'doc','pages':[{'blocks':[b]}],'annotations':[],'proposals':[]}
    for s in writing.sentences(text,'b')[:2]:writing.add_annotation(doc,b,{**s,'body':'Improve clarity.'})
    return doc


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old_data=app.DATA;app.DATA=Path(self.temp.name);app.init_store()
        self.old_complete=app.request_completion;self.calls=[];self.config={'model':'mock','base_url':'http://localhost/v1','api_key':''}
        def complete(messages,config):
            self.calls.append(messages);config['_last_usage']={'prompt_tokens':100,'completion_tokens':30}
            quote=json.loads(messages[-1]['content'])['target']
            return json.dumps({'replacement':quote.replace('result','finding'),'translation':'测试译文','rationale':'按批注修改'})
        app.request_completion=complete
        self.doc=paper()
        with app.connect() as c:c.execute('INSERT INTO documents VALUES (?,?,?,NULL,?,?)',('doc','test.pdf','ready',json.dumps(self.doc),0))

    def tearDown(self):
        app.request_completion=self.old_complete;app.DATA=self.old_data;self.temp.cleanup()

    def create(self,limit=64000):
        p=batch.plan(app.load_doc('doc'))
        return batch.create(app,app.load_doc('doc'),{'fingerprint':p['fingerprint'],'input_limit':limit},self.config)

    def test_overlap_merges_but_disjoint_sentences_stay_separate(self):
        d=paper();b=d['pages'][0]['blocks'][0]
        writing.add_annotation(d,b,{'start':4,'end':16,'body':'Avoid overclaiming.'})
        p=batch.plan(d)
        self.assertEqual(p['total'],2);self.assertEqual(p['annotation_count'],3)
        self.assertEqual(p['items'][0]['quote'],'The first result is stable.')
        self.assertEqual(len(p['items'][0]['notes']),2)
        self.assertNotIn('third',p['items'][-1]['quote'])

    def test_serial_requests_do_not_accumulate_history_and_are_reused(self):
        b=self.create();batch.run(app,b['id'],self.config,threading.Event())
        result=batch.load(app,b['id']);self.assertEqual(result['status'],'completed');self.assertEqual(len(self.calls),2)
        self.assertEqual(result['reported_input_tokens'],200)
        for messages in self.calls:
            self.assertEqual(len(messages),2)
            payload=json.loads(messages[-1]['content'])
            self.assertEqual(len(payload['annotations']),1)
            self.assertNotIn('finding',json.dumps(payload))
            self.assertLessEqual(payload['manuscript_context']['estimated_input_tokens'],8000)
        again=self.create();self.assertEqual(again['id'],b['id'])
        batch.run(app,b['id'],self.config,threading.Event());self.assertEqual(len(self.calls),2)
        self.assertEqual(app.load_doc('doc')['pages'][0]['blocks'][0]['text'],self.doc['pages'][0]['blocks'][0]['text'])

    def test_cancel_keeps_finished_item_and_resume_only_calls_remaining(self):
        cancel=threading.Event();original=app.request_completion
        def stop(messages,config):
            result=original(messages,config);cancel.set();return result
        app.request_completion=stop;b=self.create();batch.run(app,b['id'],self.config,cancel)
        stopped=batch.load(app,b['id']);self.assertEqual(stopped['status'],'cancelled')
        self.assertEqual([i['status'] for i in stopped['items']],['done','pending'])
        app.request_completion=original;batch.run(app,b['id'],self.config,threading.Event());self.assertEqual(len(self.calls),2)
        self.assertEqual(len(app.load_doc('doc')['proposals']),2)

    def test_budget_pause_and_restart_accounting(self):
        b=self.create();b['reserved_tokens']=b['input_limit']-1;batch.save(app,b)
        batch.run(app,b['id'],self.config,threading.Event());paused=batch.load(app,b['id'])
        self.assertEqual(paused['status'],'budget_paused');self.assertEqual(len(self.calls),0)
        paused['input_limit']+=32000;paused['status']='running';paused['items'][0]['status']='running';batch.save(app,paused)
        app.init_store();restored=batch.load(app,b['id'])
        self.assertEqual(restored['status'],'interrupted');self.assertEqual(restored['reserved_tokens'],63999)
        self.assertEqual(restored['items'][0]['status'],'pending')
        batch.run(app,b['id'],self.config,threading.Event());self.assertEqual(batch.load(app,b['id'])['status'],'completed')

    def test_changed_note_stops_and_provider_auth_error_stops_fanout(self):
        b=self.create();d=app.load_doc('doc');d['annotations'][0]['body']='A changed instruction.';app.save_doc('doc',d)
        batch.run(app,b['id'],self.config,threading.Event());self.assertEqual(batch.load(app,b['id'])['status'],'conflict');self.assertFalse(self.calls)
        b=self.create()
        def reject(*_):self.calls.append('rejected');raise ValueError('API 返回 HTTP 401。')
        app.request_completion=reject;batch.run(app,b['id'],self.config,threading.Event())
        self.assertEqual(len(self.calls),1);self.assertEqual(batch.load(app,b['id'])['status'],'partial')

    def test_multi_edit_one_revision_and_overlap_preflight(self):
        raw=b'\\documentclass{article}\n\\begin{document}\nFirst original sentence. Second original sentence.\n\\end{document}'
        meta=lp.create(app.DATA,raw,'main.tex');pid=meta['id']
        proposals=[{'id':'a','quote':'First original sentence.','replacement':'A much longer first replacement sentence.'},
                   {'id':'b','quote':'Second original sentence.','replacement':'Short second.'}]
        invalid=[proposals[0],{'id':'c','quote':'original sentence. Second','replacement':'Overlap'}]
        with self.assertRaises(ValueError):lp.apply_batch(app.DATA,pid,invalid,1)
        self.assertEqual(lp.read_source(app.DATA,pid)['text'],raw.decode())
        meta=lp.apply_batch(app.DATA,pid,proposals,1)
        self.assertEqual(meta['revision'],2)
        expected=raw.decode().replace('First original sentence.',proposals[0]['replacement']).replace('Second original sentence.',proposals[1]['replacement'])
        self.assertEqual(lp.read_source(app.DATA,pid)['text'],expected)
        with self.assertRaises(ValueError):lp.apply_batch(app.DATA,pid,proposals,1)
