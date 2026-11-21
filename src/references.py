"""Get reviewed build inputs without distributing the owner's firmware."""

from ftplib import FTP, all_errors
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.request import urlopen

import build_overlay


COMPILER_URL = ('https://repo.maven.apache.org/maven2/org/eclipse/jdt/core/compiler/'
                'ecj/4.6.1/ecj-4.6.1.jar')
COMPILER_SIZE = 2440899
CONVERTER_REVISION = '9eeb45bbf14bf8afe3452c7be96a4d1f0206a286'
CONVERTER_URL = f'https://raw.githubusercontent.com/luka-dev/jxe2jar/{CONVERTER_REVISION}/src/'
CONVERTER_FILES = {
    'bitstring.py': (3613, '04daec6b4f5aa674745708046c7684d7f9b1e89fcf76bfb9086110925e24cee0'),
    'bytecode.py': (46792, 'ed6587a65168b15328b7d1ea8c34f554e9f543531a159e41a653897364aa51b4'),
    'common.py': (9976, 'be0371b82224ec56940db537174283d9a30489f8f6ad4f53f4c15c2922b5c6db'),
    'constpool.py': (19898, '66da7ba7769296c69b5fef82c9276fcdea47bebfd2ea73d7c5ebc3405c7334a4'),
    'jxe.py': (27066, '82dd48ee04e102702955cc09f9bbd4412edbef949d4935da76ddae6e62a89039'),
    'jxe2jar.py': (32996, '9f56143ae6ae53f3f3b1ebcd7eb8a45a089cc65ccf9fb5535d760bd10585b7c9'),
}
JXE_SHA256 = '5002efe6e479dade925893387200a1014bcc0ea06b38fd70acd9c8a00b914594'
DEVICE_FILES = (
    ('/ifs1/MIBHMI.jxe', 'MIBHMI.jxe', 39690780, JXE_SHA256),
    ('/extbin/apps/J9/lib/jclFoundation11/classes.zip', 'j9-foun11-classes.zip',
     3230917, build_overlay.REFERENCES['bootclasses']),
)


def bounded_writer(stream, limit):
    def write(chunk):
        if stream.tell() + len(chunk) > limit:
            raise ValueError('The file is larger than the supported version.')
        stream.write(chunk)
    return write


def download_verified(url, target, limit, checksum):
    with urlopen(url, timeout=20) as response, target.open('xb') as stream:
        if response.geturl() != url:
            raise ValueError(f'{target.name} download moved away from its reviewed address.')
        write = bounded_writer(stream, limit)
        for chunk in iter(lambda: response.read(64 * 1024), b''):
            write(chunk)
    build_overlay.verify_file(target, checksum)


def compiler_download(cache):
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = cache / 'ecj-4.6.1.jar'
    checksum = build_overlay.REFERENCES['compiler']
    if destination.is_file():
        build_overlay.verify_file(destination, checksum)
        return destination
    with tempfile.TemporaryDirectory(prefix='.download-', dir=cache) as temporary:
        staged = Path(temporary) / destination.name
        download_verified(COMPILER_URL, staged, COMPILER_SIZE, checksum)
        staged.replace(destination)
    return destination


def converter_download(cache):
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = cache / f'jxe2jar-{CONVERTER_REVISION}'
    if not destination.exists() and not destination.is_symlink():
        with tempfile.TemporaryDirectory(prefix='.converter-', dir=cache) as temporary:
            staging = Path(temporary) / 'source'
            staging.mkdir()
            for name, (size, checksum) in CONVERTER_FILES.items():
                download_verified(CONVERTER_URL + name, staging / name, size, checksum)
            try:
                staging.rename(destination)
            except OSError:
                if not destination.is_dir():
                    raise

    if destination.is_symlink() or not destination.is_dir() or {path.name for path in destination.iterdir()} != set(CONVERTER_FILES):
        raise ValueError('The cached JXE converter is incomplete or contains unexpected files.')
    for name, (_, checksum) in CONVERTER_FILES.items():
        path = destination / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'The cached converter file {name} is invalid.')
        build_overlay.verify_file(path, checksum)
    return destination / 'jxe2jar.py'


def read_device(host, source, username, password, folder):
    source_address = (str(source), 0) if source is not None else None
    try:
        with FTP(timeout=10, source_address=source_address) as ftp:
            ftp.connect(str(host))
            ftp.login(username, password)
            for remote, name, size, checksum in DEVICE_FILES:
                path = folder / name
                with path.open('xb') as stream:
                    ftp.retrbinary('RETR ' + remote, bounded_writer(stream, size), blocksize=64 * 1024)
                build_overlay.verify_file(path, checksum)
    except all_errors as error:
        raise ValueError('Could not read both files using the head unit’s existing FTP service. Check your connection, login and file access, or use a local backup.') from error
    return folder / DEVICE_FILES[0][1], folder / DEVICE_FILES[1][1]


def convert_hmi(converter, raw_hmi, target):
    build_overlay.verify_file(raw_hmi, JXE_SHA256)
    # The converter is a local tool selected by the user. Keep its output private.
    log = target.with_suffix('.conversion.log')
    with log.open('wb') as output:
        script = converter.resolve()
        try:
            subprocess.run([sys.executable, '-B', str(script), str(raw_hmi.resolve()), str(target.resolve())],
                           cwd=script.parent, stdout=output, stderr=subprocess.STDOUT, check=True, timeout=180)
        except subprocess.SubprocessError as error:
            raise ValueError('The selected JXE converter could not finish. Check that it runs with its companion files.') from error
    build_overlay.read_verified_hmi(target)
