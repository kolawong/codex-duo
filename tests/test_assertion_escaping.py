"""Offline reproduction and standalone assertion regression."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'plugins/codex-duo/skills/workflow/scripts/assert_bytes.py'


class AssertionEscapingTests(unittest.TestCase):
    def test_json_roundtrip_and_second_decode_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            probe = Path(directory) / 'probe.txt'
            probe.write_bytes(bytes.fromhex('61667465720a'))
            code = "from pathlib import Path; assert Path(__import__('sys').argv[1]).read_bytes() == b'after\\n'"
            argv = [sys.executable, '-B', '-c', code, str(probe)]
            decoded = json.loads(json.dumps(argv))
            self.assertEqual(decoded, argv)
            self.assertEqual(subprocess.run(decoded, capture_output=True).returncode, 0)
            broken = decoded.copy()
            broken[3] = broken[3].encode().decode('unicode_escape')
            result = subprocess.run(broken, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn(b'SyntaxError', result.stderr)
            self.assertNotEqual(json.loads(json.dumps(broken)), argv)

    def test_script_handles_paths_and_literal_backslashes(self):
        with tempfile.TemporaryDirectory() as directory:
            probe = Path(directory) / 'space quote\' backslash\\ probe.txt'
            for payload in (b'after\n', b'after\\n', b'after\r\n', b'', bytes(range(256))):
                probe.write_bytes(payload)
                argv = [sys.executable, '-B', str(SCRIPT), str(probe), payload.hex()]
                self.assertEqual(subprocess.run(json.loads(json.dumps(argv)), capture_output=True).returncode, 0)
            probe.write_bytes(b'after\\n')
            result = subprocess.run([sys.executable, '-O', str(SCRIPT), str(probe), '61667465720a'], capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn(b'FAIL', result.stderr)
            self.assertEqual(subprocess.run([sys.executable, str(SCRIPT), str(probe), 'not-hex'], capture_output=True).returncode, 2)
            probe.unlink()
            self.assertEqual(subprocess.run([sys.executable, str(SCRIPT), str(probe), '00'], capture_output=True).returncode, 1)
