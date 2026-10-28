import copy
import tempfile
import unittest
from pathlib import Path
import latex_project as lp
import layout_cleanup
import context_manager


class RepairTests(unittest.TestCase):
    def test_merged_review_numbers_and_folios_after_cover_pages(self):
        doc={'pages':[]}
        for page in range(4,6):
            blocks=[{'id':f'run-{page}','page':page,'text':'1 2 3 4 5 6 7 8','bbox':[.047,.24,.062,.55]},
                    {'id':f'single-{page}','page':page,'text':'9','bbox':[.047,.57,.062,.58]},
                    {'id':f'folio-{page}','page':page,'text':str(page-3),'bbox':[.914,.071,.920,.080]},
                    {'id':f'body-{page}','page':page,'text':'1 2 3 4 5 6 7 8','bbox':[.2,.24,.6,.55]},
                    {'id':f'eq-{page}','page':page,'text':'(9)','bbox':[.95,.57,.97,.58],'source_only':True}]
            doc['pages'].append({'blocks':blocks})
        original=copy.deepcopy(doc)
        layout_cleanup.annotate(doc)
        self.assertEqual(doc['layout_cleanup']['hidden_count'],6)
        for p in doc['pages']:
            self.assertEqual([b.get('layout_ignored') for b in p['blocks']],['审稿行号','审稿行号','页码',None,None])
        self.assertEqual([[b['text'] for b in p['blocks']] for p in doc['pages']],[[b['text'] for b in p['blocks']] for p in original['pages']])

    def test_gutter_sequences_and_folios_not_equations_or_body_numbers(self):
        doc={'pages':[]}
        for page in range(2):
            blocks=[{'id':f'{page}-{n}','page':page,'text':str(n+1+page*20),'bbox':[.94,.1+n*.04,.96,.11+n*.04],'kind':'paragraph'} for n in range(15)]
            blocks.extend([{'id':f'folio-{page}','page':page,'text':str(page+1),'bbox':[.49,.90,.51,.91]},
                           {'id':f'body-{page}','page':page,'text':'24','bbox':[.4,.5,.42,.52]},
                           {'id':f'eq-{page}','page':page,'text':'(24)','bbox':[.94,.5,.97,.52],'source_only':True}])
            doc['pages'].append({'blocks':blocks})
        before=copy.deepcopy(doc);layout_cleanup.annotate(doc)
        self.assertEqual(doc['layout_cleanup']['hidden_count'],32)
        self.assertFalse(doc['pages'][0]['blocks'][-2].get('layout_ignored'))
        self.assertFalse(doc['pages'][0]['blocks'][-1].get('layout_ignored'))
        self.assertEqual([b['text'] for p in before['pages'] for b in p['blocks']],[b['text'] for p in doc['pages'] for b in p['blocks']])
        rows,_=context_manager.index(doc)
        self.assertEqual([r['block_id'] for r in rows],['body-0','body-1'])

    def test_source_map_typography_and_preamble_linebreak(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            raw=r'''\documentclass{article}
\newcommand{\placeholder}{Text\\[2pt]}
\begin{document}
The clean-speech structure is efficient.
Do not edit \textbf{hidden words}.
Math \[x+y\] is protected.
\end{document}'''
            meta=lp.create(root,raw.encode(),'main.tex')
            match=lp.locate(root,meta['id'],'The cleanspeech structure is eﬃcient.')
            self.assertTrue(match['available']);self.assertEqual(match['raw_before'],'The clean-speech structure is efficient.')
            self.assertFalse(lp.locate(root,meta['id'],'hidden words')['available'])
            self.assertFalse(lp.locate(root,meta['id'],'x+y')['available'])
            lp.apply(root,meta['id'],{'id':'test','quote':'The cleanspeech structure is eﬃcient.','replacement':'The speech structure is efficient.'},1)
            text=lp.read_source(root,meta['id'])['text']
            self.assertEqual(text,raw.replace('The clean-speech structure is efficient.','The speech structure is efficient.'))

    def test_editor_revision_hash_and_path_guards(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);meta=lp.create(root,b'\\documentclass{article}\n\\begin{document}\nOriginal.\n\\end{document}','main.tex')
            current=lp.read_source(root,meta['id'])
            updated=current['text'].replace('Original.','Revised.')
            meta=lp.edit_source(root,meta['id'],'main.tex',updated,1,current['hash'])
            self.assertEqual(meta['revision'],2)
            self.assertEqual(lp.read_source(root,meta['id'])['text'],updated)
            self.assertTrue((root/'projects'/meta['id']/'history'/meta['history'][-1]['backup']).exists())
            with self.assertRaises(ValueError):lp.edit_source(root,meta['id'],'main.tex',updated,1,current['hash'])
            with self.assertRaises(ValueError):lp.read_source(root,meta['id'],'../meta.json')
            with self.assertRaises(ValueError):lp.edit_source(root,meta['id'],'main.tex','x',2,'incorrect')
