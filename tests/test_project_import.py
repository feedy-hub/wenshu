import io
import tempfile
import unittest
import zipfile
from pathlib import Path

import pymupdf
import latex_project as project


def sample_files():
    picture=pymupdf.open();page=picture.new_page(width=120,height=70)
    page.insert_text((10,35),'Diagram',fontsize=14)
    image=picture.tobytes();picture.close()
    source=r'''\documentclass{article}
\usepackage{graphicx}
\begin{document}
The imported figure and citation are present.\cite{sample}
\includegraphics[width=2cm]{figures/diagram.pdf}
\bibliographystyle{plain}
\bibliography{references}
\end{document}'''.encode()
    bibliography=b'@article{sample, author={A. Writer}, title={Imported Reference}, journal={Test Journal}, year={2026}}'
    return [('Paper Workspace/main.tex',source),('Paper Workspace/references.bib',bibliography),('Paper Workspace/figures/diagram.pdf',image)]


class ProjectImportTests(unittest.TestCase):
    def test_folder_paths_compile_with_picture_and_bibtex(self):
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder);meta=project.create_files(data,sample_files(),'Paper Workspace')
            self.assertEqual(meta['main_file'],'main.tex')
            self.assertEqual(meta['file_count'],3)
            self.assertEqual(meta['missing_files'],[])
            _,pdf=project.compile_project(data,meta['id'])
            with pymupdf.open(stream=pdf,filetype='pdf') as result:
                text=' '.join(page.get_text() for page in result)
            self.assertIn('Imported reference',text)
            self.assertIn('The imported figure',text)

    def test_nested_zip_and_missing_file_diagnostics(self):
        files=sample_files();stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            for name,content in files:archive.writestr(name,content)
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder);meta=project.create(data,stream.getvalue(),'project.zip')
            self.assertEqual(meta['main_file'],'main.tex')
            self.assertEqual(meta['missing_files'],[])
            self.assertTrue((project.directory(data,meta['id'])/'source'/'figures'/'diagram.pdf').is_file())
            incomplete=project.create_files(data,files[:1],'Incomplete')
            self.assertEqual(set(incomplete['missing_files']),{'figures/diagram.pdf','references.bib'})
            with self.assertRaisesRegex(ValueError,'项目缺少编译文件'):
                project.compile_project(data,incomplete['id'])
            self.assertEqual(project.load(data,incomplete['id'])['revision'],1)

    def test_rejects_folder_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                project.create_files(Path(folder),[('../main.tex',sample_files()[0][1])],'Unsafe')


if __name__=='__main__':unittest.main()
