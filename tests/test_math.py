import json
import tempfile
import unittest
from pathlib import Path
import pymupdf as fitz
import latex_project as lp
from parser import parse_pdf
import writing
from math_layout import inline_math, is_math, mask_formula_crop

class MathTests(unittest.TestCase):
    def test_formula_mask_removes_neighboring_line_ink(self):
        from types import SimpleNamespace
        pix=fitz.Pixmap(fitz.csRGB,fitz.IRect(30,40,50,60),False)
        pix.clear_with(0)
        page=SimpleNamespace(rect=fitz.Rect(0,0,100,100))
        mask_formula_crop(pix,page,{'clip_boxes':[[.35,.45,.4,.5]]},scale=1)
        self.assertEqual(pix.pixel(0,0),(255,255,255))
        self.assertEqual(pix.pixel(6,6),(0,0,0))
        self.assertEqual(pix.pixel(15,15),(255,255,255))

    def test_dehyphenated_line_keeps_formula_offsets_and_newtx_symbols(self):
        def span(text,font,x):
            return {'text':text,'font':font,'bbox':[x,10,x+len(text)*5,22],'size':10,'origin':[x,20]}
        spans=[span('Let ','Roman',0),span('𝑥','LibertineMathMI',20),span('∈','txsys',25),span('R','txsym',30),span(' corre-','Roman',35)]
        lines=[{'text':''.join(s['text'] for s in spans),'spans':spans,'size':10,'bbox':[0,10,70,22]},
               {'text':'spond to the input.','spans':[span('spond to the input.','Roman',0)],'size':10,'bbox':[0,25,90,37]}]
        text='Let 𝑥∈R correspond to the input.'
        runs=inline_math(lines,text,None,lambda box,_:list(box))
        self.assertEqual(len(runs),1)
        self.assertEqual((runs[0]['start'],runs[0]['end'],runs[0]['text']),(4,7,'𝑥∈R'))
        self.assertAlmostEqual(runs[0]['baseline_offset'],-2.2)
        self.assertTrue(is_math({'font':'ABCDEF+txmiaX'}))
        self.assertTrue(is_math({'font':'txexs'}))

    def test_formula_regions_preserve_prose_and_inline_offsets(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp)
            source=(Path(__file__).resolve().parents[1]/'samples/formula-demo.tex').read_bytes()
            project=lp.create(data,source,'formula-demo.tex')
            _,pdf=lp.compile_project(data,project['id'])
            path=data/'sample.pdf';path.write_bytes(pdf)
            doc=parse_pdf(path);blocks=[b for p in doc['pages'] for b in p['blocks']]
            equations=[b for b in blocks if b['kind']=='equation' and b.get('source_only')]
            self.assertGreaterEqual(len(equations),2)
            self.assertTrue(all('This sentence after' not in b['text'] for b in equations))
            self.assertTrue(any('This sentence after' in b['text'] and not b.get('source_only') for b in blocks))
            inline=next(b for b in blocks if 'We represent' in b['text'])
            self.assertIn('The expression remains attached',inline['text'])
            self.assertGreaterEqual(len(inline['math_runs']),2)
            for r in inline['math_runs']:
                self.assertEqual(inline['text'][r['start']:r['end']],r['text'])
                self.assertGreater(r['bbox'][2],r['bbox'][0])
            with fitz.open(path) as f:
                for b in equations:
                    p=f[b['page']];box=b['bbox'];rect=fitz.Rect(box[0]*p.rect.width,box[1]*p.rect.height,box[2]*p.rect.width,box[3]*p.rect.height)
                    pix=p.get_pixmap(clip=rect)
                    self.assertTrue(any(v<100 for v in pix.samples))

    def test_formula_placeholders_are_exact_and_checked_per_sentence(self):
        b={'id':'b','text':'Use x_i here. Keep y_j there.','math_runs':[{'start':4,'end':7},{'start':19,'end':22}]}
        source=writing.protected_text(b)
        self.assertEqual(source,'Use [[MATH_0]] here. Keep [[MATH_1]] there.')
        for bad in ['漏掉公式','[[MATH_0]] [[MATH_0]]']:
            with self.assertRaises(ValueError):writing.validate_math(source,bad)
        parts=writing.sentences(b['text'],'b')
        def mock(*_):return json.dumps({'segments':[{'id':parts[0]['id'],'text':'使用 [[MATH_0]]。'},{'id':parts[1]['id'],'text':'保留 [[MATH_1]]。'}]})
        out=writing.aligned_translation(b,{'target':'中文'},mock)
        self.assertIn('[[MATH_1]]',out['text'])
        def wrong(*_):return json.dumps({'segments':[{'id':parts[0]['id'],'text':'使用 [[MATH_1]]。'},{'id':parts[1]['id'],'text':'保留 [[MATH_0]]。'}]})
        with self.assertRaises(ValueError):writing.aligned_translation(b,{'target':'中文'},wrong)
