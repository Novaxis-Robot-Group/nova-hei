"""从构建产物验证独立交付，不访问实际模型或本体。"""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]


class PackageTests(unittest.TestCase):
    def test_wheel_resources_and_offline_entry_outside_repository(self):
        with tempfile.TemporaryDirectory(prefix='agent-package-') as directory:
            temporary = Path(directory)
            build = subprocess.run([
                sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation',
                '--wheel-dir', str(temporary), str(ROOT),
            ], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            wheel = next(temporary.glob('*.whl'))
            installed = temporary / 'installed'
            with zipfile.ZipFile(wheel) as archive:
                names = archive.namelist()
                self.assertTrue(any(name.endswith("/LICENSE") for name in names))
                self.assertTrue(any(name.endswith("/NOTICE") for name in names))
                self.assertIn('nova_hei/agent/memory/trajectory.py', names)
                self.assertIn('nova_hei/agent/tools/target_watch.py', names)
                self.assertIn('nova_hei/contracts/detection.py', names)
                self.assertIn('nova_hei/app/detector/server.py', names)
                metadata = archive.read(next(name for name in names if name.endswith('/METADATA'))).decode()
                self.assertIn('Name: nova-hei\n', metadata)
                entrypoints = archive.read(next(name for name in names if name.endswith('/entry_points.txt'))).decode()
                self.assertIn('nova-hei = nova_hei.app.agent.main:main', entrypoints)
                for line in metadata.splitlines():
                    if line.startswith('Requires-Dist:') and any(word in line.lower() for word in ('torch', 'ultralytics', 'clip ', 'lap')):
                        self.assertIn('extra == "detector"', line)
                self.assertFalse(any(name.endswith(('.pt', '.onnx')) for name in names))
                for module in ('memory/topology.py', 'model/observation.py', 'model/completion.py'):
                    self.assertIn('nova_hei/agent/' + module, names)
                self.assertIn('nova_hei/agent/skills/scan/skill.py', names)
                for module in ('registry.py', 'search_navigation.py', 'approach_target.py',
                               'object_search/context.py'):
                    self.assertIn('nova_hei/agent/skills/' + module, names)
                self.assertNotIn('nova_hei/agent/core/monitor.py', names)
                self.assertNotIn('nova_hei/agent/skills/object_search/skill.py', names)
                self.assertIn('nova_hei/agent/skills/object_search/target.py', names)
                self.assertNotIn('nova_hei/agent/skills/object_search/session.py', names)
                self.assertFalse(any(name.startswith(('nova_hei/robots/', 'nova_hei/navigation/', 'nova_hei/vln/', 'nova_hei/app/deployments/')) for name in names))
                self.assertEqual(
                    [name for name in names if name.startswith('nova_hei/app/') and name.count('/') == 2],
                    ['nova_hei/app/__init__.py'],
                )
                for relative in ('agent.toml', 'prompts/common.md', 'prompts/go2-office.md', 'prompts/scheduling.md'):
                    self.assertEqual(archive.read('nova_hei/app/agent/resources/' + relative),
                                     (ROOT / 'configs' / relative).read_bytes())
            # 实际安装 wheel，并从仓库外验证生成的 CLI，避免源码路径掩盖打包遗漏。
            install = subprocess.run([
                sys.executable, '-m', 'pip', 'install', '--no-deps', '--no-compile',
                '--target', str(installed), str(wheel),
            ], cwd=temporary, capture_output=True, text=True)
            self.assertEqual(install.returncode, 0, install.stdout + install.stderr)
            environment = {**os.environ, 'PYTHONPATH': str(installed), 'PYTHONNOUSERSITE': '1'}
            cli = installed / 'bin' / 'nova-hei'
            for arguments in (['--help'], ['--demo', '--output', str(temporary / 'cli-runs')]):
                result = subprocess.run([str(cli), *arguments], cwd=temporary,
                                        env=environment, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            script = """
import asyncio, json, pathlib, sys
sys.path.insert(0, sys.argv[1])
from nova_hei import agent
from nova_hei.app.agent.main import run_demo
from nova_hei.app.agent.settings import standalone_settings
assert pathlib.Path(agent.__file__).is_relative_to(sys.argv[1])
record, directory = asyncio.run(run_demo(standalone_settings(output=sys.argv[2], api_key='')))
assert record['status'] == 'completed', record
assert (directory / 'index.html').is_file()
assert (directory / 'memory.sqlite3').is_file()
print(json.dumps({'status':record['status']}))
"""
            run = subprocess.run([sys.executable, '-I', '-c', script, str(installed), str(temporary / 'runs')],
                                 cwd=temporary, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
