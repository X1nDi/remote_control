import ast
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from pc_controller.file_sharing import upload_large_file, UploadStream, _UPLOAD_LOCK


class FileSharingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'пример.apk'
        self.payload = b'0123456789'
        self.path.write_bytes(self.payload)
        self.calls = []
        self.override = {}
        self.modify = False

    def post(self, url, files):
        self.calls.append(url)
        name, stream, content_type = files['file']
        parts = list(iter(lambda: stream.read(), b''))
        self.assertEqual(list(map(len, parts)), [4, 4, 2])
        content = b''.join(parts)
        self.assertEqual(content, self.payload)
        if self.modify:
            self.path.write_bytes(b'changed')
        data = {'name': name, 'size': len(content), 'md5': hashlib.md5(content).hexdigest(),
                'downloadPage': 'https://gofile.io/d/Ab123'}
        data.update(self.override)
        return httpx.Response(200, json={'status':'ok','data':data},request=httpx.Request('POST',url))

    def upload(self):
        with patch('pc_controller.file_sharing.CHUNK_SIZE', 4):
            return upload_large_file(self.path, client=self)

    def test_stream_and_verified_result(self):
        result = self.upload()
        self.assertEqual(result.sha256, hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(result.url, 'https://gofile.io/d/Ab123')
        self.assertEqual(self.calls, ['https://upload.gofile.io/uploadfile'])

    def test_corrupt_result_not_published(self):
        self.override = {'md5':'bad'}
        with self.assertRaisesRegex(ValueError,'целостность'):
            self.upload()
        self.assertFalse(_UPLOAD_LOCK.locked())

    def test_untrusted_link_not_published(self):
        self.override = {'downloadPage':'https://evil.example/'}
        with self.assertRaisesRegex(ValueError,'ссылку'):
            self.upload()

    def test_concurrent_upload_rejected_without_network(self):
        with _UPLOAD_LOCK:
            with self.assertRaisesRegex(ValueError,'Уже загружается'):
                self.upload()
        self.assertEqual(self.calls, [])

    def test_empty_file_not_published(self):
        self.path.write_bytes(b'')
        with self.assertRaises(ValueError):
            self.upload()
        self.assertEqual(self.calls, [])

    def test_modified_file_not_published(self):
        self.modify = True
        with self.assertRaisesRegex(ValueError,'изменился'):
            self.upload()

    def test_monotonic_upload_budget(self):
        stream = UploadStream(io.BytesIO(b'abc'))
        with patch('pc_controller.file_sharing.time.monotonic', return_value=stream.started + 3601):
            with self.assertRaisesRegex(ValueError,'время'):
                stream.read()

    def test_both_download_routes_delegate_large_files(self):
        tree = ast.parse(Path('pc_controller/bot_service.py').read_text(encoding='utf-8-sig'))
        routes = [ast.unparse(n) for n in ast.walk(tree) if isinstance(n, ast.If)
                  and ast.unparse(n.test) == 'size > MAX_DOWNLOAD_FILE_SIZE']
        self.assertEqual(len(routes), 2)
        for route in routes:
            self.assertIn('await self._share_large_file(update, target)',route)
            self.assertIn('return',route)

    def test_http_error_does_not_expose_details(self):
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503))) as client:
            with self.assertRaisesRegex(ValueError,'не завершил'):
                upload_large_file(self.path, client=client)


if __name__ == '__main__':
    unittest.main()
