import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import build_overlay
from src import references


def digest(data):
    return hashlib.sha256(data).hexdigest()


class ReferenceTests(unittest.TestCase):
    def test_converter_checks_every_download_and_cached_file(self):
        source = {'common.py': b'helper', 'jxe2jar.py': b'converter'}
        manifest = {name: (len(data), digest(data)) for name, data in source.items()}

        def response(url, timeout):
            download = io.BytesIO(source[url.rsplit('/', 1)[1]])
            download.geturl = lambda: url
            return download

        with tempfile.TemporaryDirectory() as directory, patch.object(references, 'CONVERTER_FILES', manifest):
            cache = Path(directory)
            with patch.object(references, 'urlopen', side_effect=response) as download:
                converter = references.converter_download(cache)
                self.assertEqual(converter.read_bytes(), b'converter')
                self.assertEqual(references.converter_download(cache), converter)
                self.assertEqual([call.args[0] for call in download.call_args_list],
                                 [references.CONVERTER_URL + name for name in source])
                (converter.parent / 'common.py').write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'SHA-256'):
                    references.converter_download(cache)

    def test_compiler_cached_only_when_checksum_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(build_overlay.REFERENCES, {'compiler': digest(b'approved')}):
                response = io.BytesIO(b'unexpected')
                response.geturl = lambda: references.COMPILER_URL
                with patch.object(references, 'urlopen', return_value=response):
                    with self.assertRaisesRegex(ValueError, 'SHA-256'):
                        references.compiler_download(root)
                self.assertEqual(list(root.iterdir()), [])

                response = io.BytesIO(b'approved')
                response.geturl = lambda: references.COMPILER_URL
                with patch.object(references, 'urlopen', return_value=response) as download:
                    self.assertEqual(references.compiler_download(root).read_bytes(), b'approved')
                    self.assertEqual(references.compiler_download(root).read_bytes(), b'approved')
                    download.assert_called_once_with(references.COMPILER_URL, timeout=20)

    def test_device_uses_only_two_authorized_reads(self):
        content = {'/first': b'first', '/second': b'second'}
        files = tuple((path, path[1:], len(data), digest(data)) for path, data in content.items())
        with tempfile.TemporaryDirectory() as directory, patch.object(references, 'FTP') as connect:
            ftp = connect.return_value.__enter__.return_value
            ftp.retrbinary.side_effect = lambda request, callback, **kwargs: callback(content[request[5:]])
            with patch.object(references, 'DEVICE_FILES', files):
                outputs = references.read_device('192.0.2.1', None, 'example', 'secret', Path(directory))
            self.assertEqual([path.read_bytes() for path in outputs], list(content.values()))
            ftp.login.assert_called_once_with('example', 'secret')
            self.assertEqual([call.args[0] for call in ftp.retrbinary.call_args_list], ['RETR /first', 'RETR /second'])

    def test_converted_reference_checks_class_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'reference.jar'
            for timestamp in ((1980, 1, 1, 0, 0, 0), (2026, 1, 1, 0, 0, 0)):
                with zipfile.ZipFile(archive, 'w') as jar:
                    jar.writestr(zipfile.ZipInfo('Example.class', timestamp), b'approved')
                with patch.object(build_overlay, 'REFERENCE_CLASSES', {'Example.class': digest(b'approved')}):
                    self.assertEqual(build_overlay.read_verified_hmi(archive), {'Example.class': b'approved'})
            with patch.object(build_overlay, 'REFERENCE_CLASSES', {'Example.class': digest(b'unexpected')}):
                with self.assertRaisesRegex(ValueError, 'unrecognized version'):
                    build_overlay.read_verified_hmi(archive)
