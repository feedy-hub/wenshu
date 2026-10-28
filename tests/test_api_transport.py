import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


class ApiTransportTests(unittest.TestCase):
    def setUp(self):
        self.config = {'base_url': 'https://example.test/v1', 'model': 'test-model', 'api_key': 'test-key'}
        self.response = io.BytesIO(json.dumps({'choices': [{'message': {'content': '完成'}, 'finish_reason': 'stop'}]}).encode())

    def test_retries_transient_connection_failure(self):
        opener = Mock()
        opener.open.side_effect = [urllib.error.URLError('connection reset'), self.response]
        with patch.object(app.urllib.request, 'build_opener', return_value=opener), patch.object(app.time, 'sleep'):
            self.assertEqual(app.request_completion([{'role': 'user', 'content': 'test'}], self.config), '完成')
        self.assertEqual(opener.open.call_count, 2)

    def test_explains_invalid_json_after_retry(self):
        opener = Mock()
        opener.open.side_effect = [io.BytesIO(b'<html>unavailable</html>'), io.BytesIO(b'<html>unavailable</html>')]
        with patch.object(app.urllib.request, 'build_opener', return_value=opener), patch.object(app.time, 'sleep'):
            with self.assertRaisesRegex(ValueError, '响应不是有效 JSON'):
                app.request_completion([{'role': 'user', 'content': 'test'}], self.config)
        self.assertEqual(opener.open.call_count, 2)


if __name__ == '__main__':
    unittest.main()
