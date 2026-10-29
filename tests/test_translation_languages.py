import copy
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import app
import languages
import writing


class TranslationLanguageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = {'base_url': 'https://example.test/v1', 'model': 'test-model', 'api_key': 'in-memory-only',
                       'source': languages.DEFAULT_SOURCE, 'target': languages.DEFAULT_TARGET}
        for replacement in (patch.object(app, 'DATA', Path(self.temp.name)), patch.object(app, 'CONFIG', self.config), patch.object(app, 'JOBS', {})):
            replacement.start()
            self.addCleanup(replacement.stop)
        app.init_store()

    def request(self, path, data=None):
        class QuietHandler(app.Handler):
            def log_message(self, *_):
                pass
        with app.LocalServer(('127.0.0.1', 0), QuietHandler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}{path}',
                                                 json.dumps(data).encode() if data is not None else None,
                                                 {'Content-Type': 'application/json', 'X-Local-Token': app.TOKEN})
                with urllib.request.urlopen(request, timeout=5) as response:
                    return json.load(response)
            finally:
                server.shutdown()
                thread.join(timeout=3)

    def document(self):
        block = {'id': 'b', 'page': 0, 'kind': 'paragraph', 'text': 'The rate is 24%. It is stable.', 'excluded': False}
        doc = {'id': 'doc', 'pages': [{'blocks': [block]}], 'annotations': [], 'proposals': []}
        with app.connect() as connection:
            connection.execute('INSERT INTO documents VALUES (?,?,?,NULL,?,?)', ('doc', 'test.pdf', 'ready', json.dumps(doc), 0))
        return block

    def test_default_and_language_settings_survive_reload_without_persisting_key(self):
        boot = self.request('/api/bootstrap')
        self.assertEqual((boot['settings']['source'], boot['settings']['target']), ('英语', '简体中文'))
        self.assertNotIn('api_key', boot['settings'])
        self.assertEqual(len(boot['languages']), 13)
        self.request('/api/settings', {**self.config, 'source': '简体中文', 'target': '日语'})
        saved = json.loads((app.DATA / 'settings.json').read_text(encoding='utf-8'))
        self.assertEqual((saved['source'], saved['target']), ('简体中文', '日语'))
        self.assertNotIn('api_key', saved)
        self.assertEqual(app.CONFIG['api_key'], 'in-memory-only')
        app.CONFIG.update(source='英语', target='简体中文')
        app.init_store()
        self.assertEqual((app.CONFIG['source'], app.CONFIG['target']), ('简体中文', '日语'))

    def test_invalid_pair_leaves_saved_settings_and_key_unchanged(self):
        previous = dict(app.CONFIG)
        for source, target in [('英语', '英语'), ('英语', 'unknown'), ([], '法语'), ('自动识别', '自动识别')]:
            with self.subTest(source=source, target=target):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    self.request('/api/settings', {'base_url': 'https://new.example.test/v1', 'source': source, 'target': target})
                self.assertEqual(caught.exception.code, 400)
                self.assertEqual(app.CONFIG, previous)
                self.assertFalse((app.DATA / 'settings.json').exists())

    def test_existing_settings_without_source_remain_compatible(self):
        (app.DATA / 'settings.json').write_text(json.dumps({'base_url': self.config['base_url'], 'model': 'old-model', 'target': '简体中文'}), encoding='utf-8')
        app.init_store()
        self.assertEqual((app.CONFIG['source'], app.CONFIG['target'], app.CONFIG['model']), ('英语', '简体中文', 'old-model'))

    def test_paragraph_and_sentence_prompts_use_selected_languages(self):
        for source, target, source_name, target_name in [('简体中文', '英语', 'Simplified Chinese', 'English'), ('日语', '法语', 'Japanese', 'French'), ('自动识别', '阿拉伯语', 'Detect', 'Arabic')]:
            config = {**self.config, 'source': source, 'target': target}
            captured = []
            def complete(messages, _):
                captured.append(messages[0]['content'])
                if 'segments' in messages[-1]['content']:
                    rows = json.loads(messages[-1]['content'])['segments']
                    return json.dumps({'segments': [{'id': row['id'], 'text': 'Translated 24%.'} for row in rows]})
                return 'Translated 24%.'
            with patch.object(app, 'request_completion', side_effect=complete):
                app.request_translation('学术正文', config)
            writing.aligned_translation({'id': 'b', 'text': '学術文です。これは例です。'}, config, complete)
            for prompt in captured:
                self.assertIn(source_name, prompt)
                self.assertIn('into ' + target_name, prompt)
                self.assertNotIn('each English', prompt)

    def test_cache_is_separate_by_language_and_existing_translation_is_preserved_on_settings_change(self):
        self.document()
        calls = []
        def complete(_, config):
            calls.append((config['source'], config['target']))
            return config['target'] + ' 24%.'
        def translate(config):
            app.JOBS['job'] = {}
            app.translate_job('job', 'doc', ['b'], config, threading.Event())
            self.assertEqual(app.JOBS['job']['status'], 'completed')
        with patch.object(app, 'request_completion', side_effect=complete):
            config = dict(self.config)
            translate(config)
            chinese = copy.deepcopy(app.find_block(app.load_doc('doc'), 'b')['translation'])
            self.request('/api/settings', {**self.config, 'target': '法语'})
            self.assertEqual(app.find_block(app.load_doc('doc'), 'b')['translation'], chinese)
            config = dict(self.config)
            translate(config)
            translate(config)
            translate({**config, 'source': '自动识别'})
        self.assertEqual(calls, [('英语', '简体中文'), ('英语', '法语'), ('自动识别', '法语')])
        self.assertEqual(app.find_block(app.load_doc('doc'), 'b')['translation']['target'], '法语')

    def test_stale_translation_confirmation_cannot_start_with_different_languages(self):
        self.config.update(target='日语')
        with patch.object(app.TRANSLATION_POOL, 'submit') as submit:
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.request('/api/translate', {'source': '英语', 'target': '简体中文'})
            self.assertEqual(caught.exception.code, 400)
            submit.assert_not_called()

    def test_rewrite_preserves_original_language_and_uses_selected_translation(self):
        block = {'id': 'b', 'page': 0, 'text': '研究结果稳定。'}
        def complete(messages, _):
            self.assertIn('original language', messages[0]['content'])
            self.assertIn('Japanese translation', messages[0]['content'])
            self.assertNotIn('revised English', messages[0]['content'])
            return json.dumps({'replacement': '研究结果较为稳定。', 'translation': '研究結果は比較的安定しています。', 'rationale': '调整语气。'})
        proposal = writing.build_proposal({'id': 'doc'}, block, {'instruction': '调整语气'}, {**self.config, 'target': '日语'}, complete)
        self.assertEqual(proposal['replacement'], '研究结果较为稳定。')
        self.assertEqual(proposal['translation_target'], '日语')

    def test_sentence_boundaries_for_unspaced_japanese_and_arabic_and_hindi(self):
        for text in ('これは例です。これは結論です。', 'هل هذا صحيح؟ نعم هذا صحيح.', 'यह पहला वाक्य है।यह दूसरा वाक्य है।'):
            with self.subTest(text=text):
                rows = writing.sentences(text, 'b')
                self.assertEqual(len(rows), 2)
                for row in rows:
                    self.assertEqual(text[row['start']:row['end']], row['text'])


if __name__ == '__main__':
    unittest.main()
