import io
import json
import re
import tempfile
import unittest
import zipfile
from pathlib import Path
import writing
import latex_project as lp
import pymupdf as fitz

class WritingTests(unittest.TestCase):
    def test_sentences_and_exact_anchors(self):
        text='As shown in Fig. 2, accuracy is 93.5%. Smith et al. report a gain. This is clear.'
        rows=writing.sentences(text,'b')
        self.assertEqual(len(rows),3)
        for r in rows:self.assertEqual(text[r['start']:r['end']],r['text'])
        self.assertEqual(len(writing.sentences('第一句。第二句。','c')),2)
        with self.assertRaises(ValueError):writing.anchor({'text':text}, {'start':0,'end':2,'quote':'wrong'})

    def test_alignment_rejects_missing_duplicate_and_wrong_order(self):
        b={'text':'First sentence. Second sentence.','id':'b'}
        rows=writing.sentences(b['text'],'b')
        correct=[{'id':r['id'],'text':'翻译'} for r in rows]
        config={'target':'中文'}
        self.assertEqual(len(writing.aligned_translation(b,config,lambda *_:json.dumps({'segments':correct}))['segments']),2)
        for bad in [correct[:1],list(reversed(correct)),[correct[0],correct[0]]]:
            with self.assertRaises(ValueError):writing.aligned_translation(b,config,lambda *_:json.dumps({'segments':bad}))

    def test_proposal_is_bounded_and_flags_numbers(self):
        b={'text':'We test 24 cases. The result is stable.','id':'b','page':0}
        doc={'id':'doc','annotations':[]};s=writing.sentences(b['text'],'b')[0]
        data={**s,'quote':s['text'],'body':'压缩表达','instruction':'保留数值','manual':'We test 25 cases.'}
        writing.add_annotation(doc,b,data)
        p=writing.build_proposal(doc,b,data)
        self.assertEqual(p['quote'],'We test 24 cases.')
        self.assertTrue(p['warnings']);self.assertEqual(len(p['annotation_ids']),1)
        self.assertEqual(b['text'],'We test 24 cases. The result is stable.')

    def test_source_mapping_and_zip_safety(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp)
            raw=b'\\documentclass{article}\n\\begin{document}\nUnique sentence. Repeat. Repeat. \\textbf{Macro sentence.}\n% Hidden sentence.\n\\end{document}'
            meta=lp.create(data,raw,'main.tex');pid=meta['id']
            self.assertTrue(lp.locate(data,pid,'Unique sentence.')['available'])
            for quote in ['Repeat.','Macro sentence.','Hidden sentence.']:self.assertFalse(lp.locate(data,pid,quote)['available'])
            p={'id':'p','quote':'Unique sentence.','replacement':'Clear sentence.'}
            lp.apply(data,pid,p,1)
            with self.assertRaises(ValueError):lp.apply(data,pid,p,1)
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w') as z:z.writestr('../escape.tex',raw)
            with self.assertRaises(ValueError):lp.create(data,stream.getvalue(),'bad.zip')
            self.assertFalse((data/'escape.tex').exists())

    def test_real_latex_rewrite_and_recompile(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp)
            raw=(Path(__file__).resolve().parents[1]/'samples'/'writing-demo.tex').read_bytes()
            meta=lp.create(data,raw,'writing-demo.tex')
            _,before=lp.compile_project(data,meta['id'])
            old=fitz.open(stream=before,filetype='pdf');text=' '.join(p.get_text() for p in old);old.close()
            self.assertIn('The system preserves the original manuscript.',text)
            proposal={'id':'manual-test','quote':'The system preserves the original manuscript.','replacement':'The workspace keeps the original manuscript intact.'}
            lp.apply(data,meta['id'],proposal,1)
            _,after=lp.compile_project(data,meta['id'])
            new=fitz.open(stream=after,filetype='pdf');newtext=' '.join(p.get_text(flags=fitz.TEXT_DEHYPHENATE) for p in new);new.close()
            normalized=' '.join(re.sub(r'(?<=\w)-\s*\n\s*(?=\w)','',newtext).split())
            self.assertIn(proposal['replacement'],normalized)
            self.assertNotIn(proposal['quote'],normalized)
            source=(lp.directory(data,meta['id'])/'source'/'main.tex').read_text(encoding='utf-8')
            self.assertEqual(source,raw.decode().replace(proposal['quote'],proposal['replacement']))
            self.assertTrue((lp.directory(data,meta['id'])/'history'/'1-main.tex').exists())

if __name__=='__main__':unittest.main()
