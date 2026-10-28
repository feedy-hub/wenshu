import hashlib
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pymupdf as fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from parser import parse_pdf, extract_lines, visual_regions

ROOT = Path(__file__).resolve().parents[1]


class ParserTests(unittest.TestCase):
    def test_adjacent_ruled_tables_split_at_second_caption(self):
        pdf = fitz.open()
        page = pdf.new_page(width=600, height=800)
        page.insert_text((380, 85), 'TABLE IV', fontsize=10)
        page.insert_text((380, 285), 'TABLE V', fontsize=10)
        for y in (105, 120, 150, 180, 250, 350, 365, 390, 420):
            page.draw_line((310, y), (560, y))
        regions = [fitz.Rect(box) for kind, box in visual_regions(page, extract_lines(page)) if kind == 'table']
        self.assertEqual(len(regions), 2)
        self.assertLess(regions[0].y1, 280)
        self.assertGreater(regions[1].y0, 285)
        pdf.close()

    def test_two_columns_and_full_width_barrier(self):
        doc = parse_pdf(ROOT / 'samples' / 'two-column-demo.pdf')
        self.assertEqual([p['layout'] for p in doc['pages']], ['two-column', 'two-column'])
        markers = ('L1.', 'L2.', 'L3.', 'R1.', 'R2.', 'R3.')
        actual = [b['text'][:3] for b in doc['pages'][0]['blocks'] if b['text'].startswith(markers)]
        self.assertEqual(actual, list(markers))
        markers2 = ('A1.', 'A2.', 'W1.', 'B1.', 'B2.', 'B3.', 'B4.')
        actual2 = [b['text'][:3] for b in doc['pages'][1]['blocks'] if b['text'].startswith(markers2)]
        self.assertEqual(actual2, list(markers2))
        first = doc['pages'][0]['blocks'][0]
        self.assertIn('Demonstration', first['text'])
        self.assertEqual(first['column'], 'wide')
        self.assertFalse(any('NOT A RESEARCH CLAIM' in b['text'] for p in doc['pages'] for b in p['blocks']))

    def test_stable_ids_and_demo_pair_coverage(self):
        a = parse_pdf(ROOT / 'samples' / 'two-column-demo.pdf')
        b = parse_pdf(ROOT / 'samples' / 'two-column-demo.pdf')
        aa = [x for p in a['pages'] for x in p['blocks']]
        bb = [x for p in b['pages'] for x in p['blocks']]
        self.assertEqual([x['id'] for x in aa], [x['id'] for x in bb])
        pairs = json.loads((ROOT / 'samples' / 'translations.json').read_text(encoding='utf-8'))
        self.assertEqual(len(pairs), len(aa))
        self.assertTrue(all(any(x['text'].startswith(prefix) for prefix in pairs) for x in aa))

    def test_anchor_rotation_and_cropbox_matches_rendered_ink(self):
        with tempfile.TemporaryDirectory() as td:
            for rotation in (0, 90, 180, 270):
                source = fitz.open()
                p = source.new_page(width=600, height=800)
                p.insert_text((130, 220), 'Anchor geometry survives page rotation.', fontsize=14)
                p.set_cropbox(fitz.Rect(70, 80, 550, 720))
                p.set_rotation(rotation)
                file = Path(td) / f'r{rotation}.pdf'
                source.save(file)
                source.close()
                parsed = parse_pdf(file)
                b = parsed['pages'][0]['blocks'][0]
                with fitz.open(file) as check:
                    pix = check[0].get_pixmap(colorspace=fitz.csGRAY, alpha=False)
                    raw = pix.samples
                    ink = [(i % pix.width, i // pix.width) for i,v in enumerate(raw) if v < 150]
                    x0,y0,x1,y1 = b['bbox']
                    matched = sum(x0 * pix.width - 2 <= x <= x1 * pix.width + 2 and y0 * pix.height - 2 <= y <= y1 * pix.height + 2 for x,y in ink)
                    self.assertGreater(len(ink), 50)
                    self.assertGreater(matched / len(ink), .99)

    def test_image_only_page_reports_limitation(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = fitz.open()
            p = pdf.new_page()
            p.draw_rect(fitz.Rect(60, 60, 350, 450), color=(.2,.2,.2), fill=(.8,.8,.8))
            file = Path(td) / 'no-text.pdf'
            pdf.save(file)
            pdf.close()
            d = parse_pdf(file)
            self.assertEqual(d['block_count'], 0)
            self.assertIn('OCR', d['pages'][0]['warnings'][0])

    def test_ruled_table_stays_one_source_region(self):
        with tempfile.TemporaryDirectory() as td:
            pdf=fitz.open()
            p=pdf.new_page(width=600,height=800)
            p.insert_text((240,70),'TABLE I',fontsize=11)
            for y in (90,115,175):
                p.draw_line((50,y),(550,y))
            for text,x,y in [('Method',60,106),('Score',340,106),('Baseline',60,137),('0.25',340,137),('Proposed',60,158),('0.50',340,158)]:
                p.insert_text((x,y),text,fontsize=10)
            p.insert_text((50,220),'This paragraph below the table must not be swallowed.',fontsize=11)
            file=Path(td)/'table.pdf';pdf.save(file);pdf.close()
            d=parse_pdf(file)
            tables=[b for b in d['pages'][0]['blocks'] if b['kind']=='table']
            self.assertEqual(len(tables),1)
            self.assertTrue(tables[0]['source_only'])
            self.assertIn('0.25',tables[0]['text'])
            self.assertTrue(any(b['text'].startswith('This paragraph') and not b.get('source_only') for b in d['pages'][0]['blocks']))

    def test_indented_references_do_not_shift_gutter(self):
        with tempfile.TemporaryDirectory() as td:
            pdf=fitz.open();p=pdf.new_page(width=612,height=792)
            remaining=p.insert_textbox(fitz.Rect(49,60,301,700),('Left column prose should precede all right references. ' * 16),fontsize=10)
            self.assertGreaterEqual(remaining,0)
            for n in range(5):
                p.insert_text((312,65+n*75),f'[{n+1}] Reference author and title.',fontsize=10)
                p.insert_textbox(fitz.Rect(330,70+n*75,563,125+n*75),'Indented continuation of the reference entry in the right column. '*3,fontsize=10)
            file=Path(td)/'references.pdf';pdf.save(file);pdf.close()
            d=parse_pdf(file)
            blocks=d['pages'][0]['blocks']
            self.assertEqual(d['pages'][0]['layout'],'two-column')
            self.assertEqual(blocks[0]['column'],'left')
            self.assertTrue(all(b['column']=='right' for b in blocks if b['text'].startswith('[')))


class MockProvider(BaseHTTPRequestHandler):
    calls = []
    def log_message(self, *args):
        pass
    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append((self.path, payload))
        out = {'choices':[{'finish_reason':'stop','message':{'content':'这是本地模拟 API 的测试译文，数值 0.25 与引用 [3] 保持不变。'}}]}
        if '"segments"' in payload['messages'][0]['content']:
            segments=json.loads(payload['messages'][1]['content'])['segments']
            out['choices'][0]['message']['content']=json.dumps({'segments':[{'id':s['id'],'text':'句级测试译文 '+str(i)} for i,s in enumerate(segments)]})
        if '"replacement"' in payload['messages'][0]['content']:
            target=json.loads(payload['messages'][1]['content'])['target']
            out['choices'][0]['message']['content']=json.dumps({'replacement':target+' Revised.','translation':'模拟改写译文','rationale':'模拟改写解释'})
        if '"summary"' in payload['messages'][0]['content']:
            out['choices'][0]['message']['content']=json.dumps({'summary':'本地测试章节摘要','terms':['codec: 编码器'],'claims':['仅为测试']})
        out['usage']={'prompt_tokens':123,'completion_tokens':45}
        body = json.dumps(out, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class LocalApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        app.DATA = Path(cls.temp.name)
        app.init_store()
        cls.server = ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.provider = ThreadingHTTPServer(('127.0.0.1',0),MockProvider)
        threading.Thread(target=cls.provider.serve_forever,daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close()
        cls.provider.shutdown(); cls.provider.server_close()
        cls.temp.cleanup()

    def request(self,path,data=None,raw=None):
        if raw is not None:
            body=raw
        else:
            body=json.dumps(data).encode() if data is not None else None
        req=urllib.request.Request(self.base+path,body,{'X-Local-Token':app.TOKEN,'Content-Type':'application/json'})
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    def test_import_translation_anchor_persistence_and_cache(self):
        content=(ROOT/'samples'/'two-column-demo.pdf').read_bytes()
        did=self.request('/api/import?name=test.pdf',raw=content)['id']
        self.assertEqual(did,self.request('/api/import?name=duplicate.pdf',raw=content)['id'])
        for _ in range(60):
            doc=self.request('/api/documents/'+did)
            if doc['status']=='ready':break
            time.sleep(.05)
        self.assertEqual(doc['status'],'ready')
        block=next(b for b in doc['pages'][0]['blocks'] if b['text'].startswith('R2.'))
        config={'base_url':f'http://127.0.0.1:{self.provider.server_port}/v1','model':'local-mock','api_key':'only-test-key'}
        self.request('/api/settings',config)
        self.assertNotIn('only-test-key',(app.DATA/'settings.json').read_text(encoding='utf-8'))
        count=len(MockProvider.calls)
        for _ in range(2):
            job=self.request('/api/translate',{'document_id':did,'block_ids':[block['id']]})['id']
            for _ in range(60):
                status=self.request('/api/jobs/'+job)
                if status['status'] not in ('queued','running'):break
                time.sleep(.05)
            self.assertEqual(status['status'],'completed',status)
        self.assertEqual(len(MockProvider.calls)-count,1)
        live=self.request('/api/documents/'+did)
        translated=app.find_block(live,block['id'])
        self.assertEqual(translated['bbox'],block['bbox'])
        self.assertEqual(translated['translation']['source'],'api')
        self.assertEqual(translated['translation']['model'],'local-mock')
        self.assertEqual(translated['translation']['source_hash'],hashlib.sha256(block['text'].encode()).hexdigest())
        self.request('/api/block',{'document_id':did,'block_id':block['id'],'translation':'手动修正','excluded':True,'move':-1})
        reread=app.load_doc(did)
        b=app.find_block(reread,block['id'])
        self.assertTrue(b['excluded'])
        self.assertEqual(b['translation']['text'],'手动修正')
        self.assertEqual(b['bbox'],block['bbox'])
        self.assertEqual(MockProvider.calls[-1][0],'/v1/chat/completions')

    def test_write_requires_local_token(self):
        req=urllib.request.Request(self.base+'/api/demo',b'{}',{'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req)
        self.assertEqual(err.exception.code,403)

    def test_context_summary_cache_preview_and_stale_guard(self):
        did=self.request('/api/import?name=context.pdf',raw=(ROOT/'samples'/'two-column-demo.pdf').read_bytes())['id']
        for _ in range(60):
            doc=self.request('/api/documents/'+did)
            if doc['status']=='ready':break
            time.sleep(.05)
        self.request('/api/settings',{'base_url':f'http://127.0.0.1:{self.provider.server_port}/v1','model':'local-mock'})
        b=next(b for b in doc['pages'][0]['blocks'] if b['text'].startswith('L2.'))
        anchor={'document_id':did,'block_id':b['id'],'quote':b['text'],'instruction':'Improve clarity.'}
        for _ in range(2):
            count=len(MockProvider.calls)
            jid=self.request('/api/context-build',{'document_id':did})['id']
            for n in range(100):
                state=self.request('/api/jobs/'+jid)
                if state['status'] not in ('queued','running'):break
                time.sleep(.02)
            self.assertEqual(state['status'],'completed',state)
            if _:self.assertEqual(len(MockProvider.calls),count)
        catalog=self.request('/api/context',{'document_id':did})
        self.assertEqual(catalog['ready'],catalog['total'])
        preview=self.request('/api/context-preview',anchor)
        proposal=self.request('/api/rewrite',{**anchor,'context_fingerprint':preview['fingerprint']})
        self.assertEqual(proposal['context'],preview)
        self.assertEqual(proposal['usage']['prompt_tokens'],123)
        self.request('/api/context-settings',{'document_id':did,'settings':{'constraints':'Keep the exact claim.'}})
        count=len(MockProvider.calls)
        with self.assertRaises(urllib.error.HTTPError) as err:
            self.request('/api/rewrite',{**anchor,'context_fingerprint':preview['fingerprint']})
        self.assertEqual(err.exception.code,400)
        self.assertEqual(len(MockProvider.calls),count)

    def test_sentence_api_cache_annotations_and_rewrite(self):
        did=self.request('/api/import?name=aligned.pdf',raw=(ROOT/'samples'/'two-column-demo.pdf').read_bytes())['id']
        for _ in range(60):
            doc=self.request('/api/documents/'+did)
            if doc['status']=='ready':break
            time.sleep(.05)
        b=next(b for b in doc['pages'][0]['blocks'] if b['text'].startswith('L2.'))
        self.request('/api/settings',{'base_url':f'http://127.0.0.1:{self.provider.server_port}/v1','model':'local-mock'})
        before=len(MockProvider.calls)
        for _ in range(2):
            jid=self.request('/api/translate',{'document_id':did,'block_ids':[b['id']],'granularity':'sentence'})['id']
            for _ in range(60):
                state=self.request('/api/jobs/'+jid)
                if state['status'] not in ('queued','running'):break
                time.sleep(.05)
            self.assertEqual(state['status'],'completed',state)
        self.assertEqual(len(MockProvider.calls)-before,1)
        b=app.find_block(self.request('/api/documents/'+did),b['id'])
        self.assertEqual([r['id'] for r in b['translation']['segments']],[s['id'] for s in b['sentences']])
        s=b['sentences'][0];anchor={'document_id':did,'block_id':b['id'],'start':s['start'],'end':s['end'],'quote':s['text']}
        note=self.request('/api/annotation',{**anchor,'body':'改善表达'})
        proposal=self.request('/api/rewrite',anchor)
        live=self.request('/api/documents/'+did)
        self.assertEqual(app.find_block(live,b['id'])['text'],b['text'])
        self.assertIn(note['id'],proposal['annotation_ids'])
        self.assertEqual(proposal['source'],'api')
        self.assertEqual(live['proposals'][-1]['id'],proposal['id'])


if __name__=='__main__':
    unittest.main(verbosity=2)
