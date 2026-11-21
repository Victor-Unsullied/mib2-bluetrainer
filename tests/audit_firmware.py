"""Run the offline Java fixtures against the stock input and every generated overlay."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
EXPECTED = {
    'auto': ('1,1', '1,2', '1,3', '3,1', '3,2', '3,3', '4,4'),
    'combustion-manual': ('1,1',),
    'combustion-automatic': ('1,2', '1,3'),
    'hybrid-manual': ('3,1',),
    'hybrid-automatic': ('3,2', '3,3'),
    'electric': ('4,4',),
}


def run(command):
    subprocess.run(command, check=True, timeout=120)


def classpath(*paths):
    return os.pathsep.join(map(str, paths))


def audit(java, javac, compiler, bootclasses, hmi_api):
    with tempfile.TemporaryDirectory(prefix='bluetrainer-audit-') as temporary:
        root = Path(temporary)
        fixtures = sorted((HERE / 'fixtures').glob('*.java'))
        for profile, pairs in EXPECTED.items():
            overlay = root / f'{profile}.jar'
            run([
                sys.executable, '-B', str(HERE.parent / 'build_overlay.py'),
                '--profile', profile, '--java', java, '--compiler', str(compiler),
                '--bootclasses', str(bootclasses), '--hmi-api', str(hmi_api), '--output', str(overlay),
            ])
            candidate_classpath = classpath(root, overlay, hmi_api)
            if profile == 'auto':
                run([javac, '-cp', candidate_classpath, '-d', str(root), *map(str, fixtures)])
                run([java, '-Xverify:all', '-cp', classpath(root, hmi_api),
                     'golf.thinkbluefix.TrainerConsumerAudit', str(hmi_api)])
            run([java, '-Xverify:all', '-cp', candidate_classpath,
                 'golf.thinkbluefix.FirmwareDefaultsAudit', *pairs])
            run([java, '-Xverify:all', '-cp', candidate_classpath,
                 'golf.thinkbluefix.TrainerConsumerAudit', str(overlay), *pairs])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--java', default='java')
    parser.add_argument('--javac', default='javac')
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--bootclasses', type=Path, required=True)
    parser.add_argument('--hmi-api', type=Path, required=True)
    args = parser.parse_args()
    audit(args.java, args.javac, args.compiler, args.bootclasses, args.hmi_api)


if __name__ == '__main__':
    main()
