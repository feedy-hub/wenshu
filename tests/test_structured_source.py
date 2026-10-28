import tempfile
import unittest
from pathlib import Path
import latex_project as lp


class StructuredSourceTests(unittest.TestCase):
    def test_acm_abstract_and_caption_preserve_macros_and_automatic_label(self):
        raw = r'''\documentclass{article}
\newcommand{\method}{AV-Codec}
\begin{abstract}
We propose \method, using clean-speech targets. \method\ improves speech.
\end{abstract}
\begin{document}
\begin{figure}
\caption{Results for \method's speech targets.}
\label{fig:results}
\end{figure}
\end{document}'''
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder); project = lp.create(data, raw.encode(), 'main.tex')
            proposals = [dict(id='a', quote='We propose AV-Codec, using cleanspeech targets. AV-Codec improves speech.', replacement='AV-Codec improves speech using clean-speech targets.'),
                         dict(id='b', quote="Figure 3: Results for AV-Codec’s speech targets.", replacement="Figure 3: Speech results for AV-Codec.")]
            self.assertTrue(all(m['available'] for m in lp.batch_matches(data,project['id'],proposals,1)))
            lp.apply_batch(data,project['id'],proposals,1)
            source = lp.read_source(data,project['id'])['text']
            self.assertIn(r'\method{} improves speech',source)
            self.assertIn(r'\caption{Speech results for \method{}.}',source)
            self.assertIn(r'\label{fig:results}',source)
            self.assertNotIn('Figure 3:',source)
            self.assertTrue(lp.locate(data,project['id'],'AV-Codec improves speech using clean-speech targets.')['available'])

    def test_unsafe_macros_math_duplicates_and_changed_label_stay_blocked(self):
        raw = r'''\documentclass{article}
\newcommand{\method}{AV-Codec}
\begin{document}
\textbf{Protected text.}
$\method + x$
Repeated \method. Repeated \method.
\begin{figure}\caption{Results for \method.}\end{figure}
\end{document}'''
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder);pid=lp.create(data,raw.encode(),'main.tex')['id']
            for quote in ('Protected text.','AV-Codec + x','Repeated AV-Codec.'):
                self.assertFalse(lp.locate(data,pid,quote)['available'])
            with self.assertRaises(ValueError):
                lp.apply_batch(data,pid,[dict(id='c',quote='Figure 3: Results for AV-Codec.',replacement='Figure 4: New results.')],1)
            self.assertEqual(lp.read_source(data,pid)['text'],raw)

    def test_selected_main_with_xspace_and_numbered_citations(self):
        raw = r'''\documentclass{article}
\newcommand{\method}{AV-Codec\xspace}
\begin{document}
The system uses prior work~\cite{first,second}. \method narrows the target.
\end{document}'''
        quote = 'The system uses prior work [2], [1]. AV-Codec narrows the target.'
        replacement = 'Prior work [1], [2] informs the system. AV-Codec narrows its target.'
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder)
            meta=lp.create_files(data,[('main.tex',raw.encode()),('alternate.tex',raw.encode())],'Workspace')
            match=lp.locate(data,meta['id'],quote)
            self.assertTrue(match['available'])
            self.assertEqual(match['file'],'main.tex')
            bad=lp.batch_matches(data,meta['id'],[dict(id='bad',quote=quote,replacement='Prior work [3] informs the system.')],1)
            self.assertFalse(bad[0]['available'])
            self.assertIn('引用编号',bad[0]['reason'])
            lp.apply_batch(data,meta['id'],[dict(id='citation',quote=quote,replacement=replacement)],1)
            updated=lp.read_source(data,meta['id'])['text']
            self.assertIn(r'Prior work~\cite{first,second} informs the system.',updated)
            self.assertIn(r'\method{} narrows its target.',updated)
            self.assertEqual((lp.directory(data,meta['id'])/'source'/'alternate.tex').read_text(),raw)
            with self.assertRaisesRegex(ValueError,'引用编号'):
                from source_mapping import replacement_source
                replacement_source('Prior work [3] informs the system.',match,{})
