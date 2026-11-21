#!/usr/bin/env python3
"""Build a local Think Blue Trainer overlay using the stock firmware's defaults."""

import argparse
import hashlib
import io
from pathlib import Path
import subprocess
import tempfile
import zipfile

from src.firmware import STOCK_CLASS_ENTRY, STOCK_CLASS_SHA256, patch_firmware


SOURCE = Path(__file__).resolve().parent / 'src/golf/thinkbluefix/FirmwareDefaults.java'
REFERENCES = {
    'compiler': '9cddda75f4a1b4469e73f44e7b61a3e897d0f657df4797f9106ffe88c4eeade0',
    'bootclasses': '02c425a49ff3e2b96751d2cd56462a01599ae0ec587c38f67ff13d4a4484ca8c',
}
CONFIG_API = 'de/vw/mib/asl/framework/api/diagnosis/config/'
COMPILE_CLASSES = (CONFIG_API + 'Access.class', CONFIG_API + 'EcoHmi.class')
REFERENCE_CLASSES = {
    STOCK_CLASS_ENTRY: STOCK_CLASS_SHA256,
    COMPILE_CLASSES[0]: 'cf68d38bcf1266203277d6c0d2d2ecf9a285d343a8c6d65ad31656826df47fba',
    COMPILE_CLASSES[1]: 'e8b47c932c32dab8955278bd60718147e71b9ee9e8b4975c86158e82e99551b1',
    'de/vw/mib/asl/framework/internal/diagnosis/variant/std2/EcoHmiImpl.class':
        '03eb1d36df8c017db0697221b2255b36ae944b8e4edf8e65de17502999d468fb',
}
PROFILES = {
    'combustion-manual': ((1, 1),),
    'combustion-automatic': ((1, 2), (1, 3)),
    'hybrid-manual': ((3, 1),),
    'hybrid-automatic': ((3, 2), (3, 3)),
    'electric': ((4, 4),),
}
HELPER_ENTRIES = {
    'golf/thinkbluefix/FirmwareDefaults.class',
    'golf/thinkbluefix/SelectedProfile.class',
}


def profile_source(profile):
    pairs = [pair for group in PROFILES.values() for pair in group] if profile == 'auto' else PROFILES[profile]
    conditions = ' || '.join(f'(engineType == {engine} && gearType == {gear})' for engine, gear in pairs)
    return (
        'package golf.thinkbluefix;\n'
        'final class SelectedProfile {\n'
        '    private SelectedProfile() { }\n'
        '    static boolean matches(int engineType, int gearType) {\n'
        f'        return {conditions};\n'
        '    }\n'
        '}\n'
    )


def verify_file(path, expected):
    with path.open('rb') as source:
        digest = hashlib.sha256()
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError(f'{path.name} SHA-256 is unfamiliar')


def read_verified_hmi(path):
    classes = {}
    with zipfile.ZipFile(path) as firmware:
        names = firmware.namelist()
        for name, expected in REFERENCE_CLASSES.items():
            if names.count(name) != 1 or firmware.getinfo(name).file_size > 1024 * 1024:
                raise ValueError(f'{path.name} lacks one unambiguous, reviewed copy of {name}')
            data = firmware.read(name)
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError(f'{path.name} has an unrecognized version of {name}')
            classes[name] = data
    return classes


def verify_references(compiler, bootclasses, hmi_api):
    verify_file(compiler, REFERENCES['compiler'])
    verify_file(bootclasses, REFERENCES['bootclasses'])
    return read_verified_hmi(hmi_api)


def build(java, compiler, bootclasses, hmi_api, profile):
    profile_code = profile_source(profile)
    firmware = verify_references(compiler, bootclasses, hmi_api)
    patched = patch_firmware(firmware[STOCK_CLASS_ENTRY])
    with tempfile.TemporaryDirectory(prefix='bluetrainer-') as temporary:
        root = Path(temporary)
        compile_api = root / 'verified-api.jar'
        with zipfile.ZipFile(compile_api, 'w') as archive:
            for name in COMPILE_CLASSES:
                archive.writestr(name, firmware[name])
        selected_profile = root / 'SelectedProfile.java'
        selected_profile.write_text(profile_code, encoding='ascii')
        classes = root / 'classes'
        classes.mkdir()
        subprocess.run([
            java, '-jar', str(compiler.resolve()), '-source', '1.4', '-target', '1.4',
            '-bootclasspath', str(bootclasses.resolve()), '-classpath', str(compile_api),
            '-d', str(classes), str(SOURCE), str(selected_profile),
        ], check=True, timeout=90)
        entries = {path.relative_to(classes).as_posix(): path.read_bytes()
                   for path in classes.rglob('*.class')}
    if entries.keys() != HELPER_ENTRIES or any(
        data[:8] != b'\xca\xfe\xba\xbe\x00\x00\x00\x30' for data in entries.values()
    ):
        raise ValueError('Unexpected Java 1.4 helper output')

    entries[STOCK_CLASS_ENTRY] = patched
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, data in sorted(entries.items()):
            entry = zipfile.ZipInfo(name)
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
    return output.getvalue()


def write_new_file(path, data):
    output = path.open('xb')
    try:
        with output:
            output.write(data)
    except OSError:
        path.unlink()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('auto', *PROFILES), default='auto',
                        help='Expected powertrain and gearbox. Auto follows the firmware classification.')
    parser.add_argument('--java', default='java', help='Java executable or full path')
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--bootclasses', type=Path, required=True)
    parser.add_argument('--hmi-api', type=Path, required=True, help='Matching local MIBHMI-analysis.jar')
    parser.add_argument('--output', type=Path, help='New local JAR for offline verification')
    args = parser.parse_args()
    try:
        data = build(args.java, args.compiler, args.bootclasses, args.hmi_api, args.profile)
        if args.output is not None:
            write_new_file(args.output, data)
    except (OSError, ValueError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        parser.exit(1, f'Overlay build failed: {error}\n')
    print(f'Built offline overlay for {args.profile}. SHA-256 {hashlib.sha256(data).hexdigest()}')
    if args.output is not None:
        print(f'Saved {args.output}')


if __name__ == '__main__':
    main()
